import { useEffect, useState } from "react";
import { Download, ExternalLink } from "lucide-react";
import { api, type JobSummary, type Profile, type ProfilePage } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { ErrorNote } from "../components/ui";
import SectionEditor from "../components/SectionEditor";
import ChatPanel from "../components/ChatPanel";
import CvCanvas from "../components/CvCanvas";

const EDITABLE = new Set(["default", "times"]);
type Tab = "chat" | "details" | "checks";

export default function Me() {
  const { profileVersion, bumpProfile } = useStore();
  const { data, error, reload } = useLoad(() => api.profile(), [profileVersion]);
  const { data: pipeline } = useLoad(() => api.applications(), []);
  const [tab, setTab] = useState<Tab>("chat");
  const [target, setTarget] = useState<number | "">("");
  const { data: targetPage } = useLoad(() => (target ? api.job(target) : Promise.resolve(null)), [target, profileVersion]);

  if (error) return <div className="p-7"><ErrorNote message={error} /></div>;
  if (!data) return <div className="p-7 text-text-2">Loading…</div>;
  const p = data.profile;
  const tid = p.preferences.template;
  const editable = EDITABLE.has(tid) && !data.master_cv;
  const done = data.checklist.filter((c) => c.done).length;
  const targets: JobSummary[] = pipeline ? pipeline.flatMap((c) => c.cards.map((card) => card.job)) : [];
  const ats = targetPage?.ats ?? null;
  function changed() { reload(); bumpProfile(); }

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(320px,400px)_minmax(0,1fr)]">
      {/* Left: talk to it, or open the details */}
      <section className="flex min-h-0 flex-col border-r border-line bg-bg-2">
        <div className="flex gap-1 border-b border-line px-3 pt-3" role="tablist">
          {([["chat", "Chat"], ["details", "Details"], ["checks", `Checks ${done}/${data.checklist.length}`]] as [Tab, string][]).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className={`-mb-px min-h-[38px] border-b-2 px-3 text-[13.5px] font-medium ${tab === k ? "border-accent text-text" : "border-transparent text-text-2 hover:text-text"}`}>{label}</button>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "chat" && <ChatPanel title="Edit your CV by chatting" />}
          {tab === "details" && <div className="h-full overflow-y-auto p-3"><Details data={data} onChange={changed} /></div>}
          {tab === "checks" && (
            <div className="h-full overflow-y-auto p-4">
              <ul>
                {data.checklist.map((c) => (
                  <li key={c.label} className={`flex items-start gap-2.5 py-2 ${c.done ? "text-text" : "text-text-2"}`}>
                    <span className={`mt-[3px] h-4 w-4 shrink-0 rounded-full border ${c.done ? "border-ok bg-ok" : "border-line-2"}`} aria-hidden />
                    <span>{c.label}{!c.done && <span className="block text-[12px] text-text-3">{c.hint}</span>}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      {/* Right: the CV itself */}
      <section className="flex min-h-0 flex-col gap-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="mr-2 text-[22px] font-extrabold">Your CV</h1>
          <select className="input w-auto" value={tid} aria-label="Template"
            onChange={(e) => api.patchProfile("preferences.template", e.target.value).then(changed)}>
            {data.templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select className="input w-auto max-w-[260px]" value={target} aria-label="Check against a job" onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Check against a job…</option>
            {targets.map((j) => <option key={j.id} value={j.id}>{j.title} · {j.company}</option>)}
          </select>
          <div className="ml-auto flex gap-2">
            <button className={`btn ${p.verified ? "" : "btn-primary"}`} onClick={() => api.patchProfile("verified", p.verified ? "false" : "true").then(changed)}>
              {p.verified ? "Verified ✓" : "Mark verified"}
            </button>
            <a className="btn" href={`/api/cv/pdf?template=${tid}`}><Download size={14} /> PDF</a>
            <a className="btn btn-quiet" href={`/api/cv/preview?template=${tid}`} target="_blank" rel="noopener" aria-label="Open in a new tab"><ExternalLink size={14} /></a>
          </div>
        </div>
        <p className="-mt-1 text-[12.5px] text-text-2">
          {editable ? "Click any text on the page to change it. Enter saves, Esc cancels. Chat, or Claude via MCP, for bigger changes." : "This template is view-only. Switch to Jobgent or Times to edit on the page, or use the chat."}
        </p>
        {target !== "" && (
          <div className="rounded-lg border border-line bg-bg-2 p-3">
            {ats ? (
              <>
                <b className="text-[13px]">{ats.percent}% of this posting's keywords are in your CV</b>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {ats.matched.map((k) => <span key={k} className="rounded-md border border-ok/40 px-2 py-0.5 text-[12.5px] text-ok">{k}</span>)}
                  {ats.missing.map((k) => <span key={k} className="rounded-md border border-bad/40 px-2 py-0.5 text-[12.5px] text-bad">{k}</span>)}
                </div>
              </>
            ) : <span className="text-[13px] text-text-2">No keywords for this job yet. It needs a score first (Anthropic key).</span>}
          </div>
        )}
        <CvCanvas template={tid} editable={editable} />
      </section>
    </div>
  );
}

/** Field saved on blur or Enter. */
function Field({ label, path, value, multiline, onSaved }: { label: string; path: string; value: string; multiline?: boolean; onSaved: () => void }) {
  const [v, setV] = useState(value);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setV(value), [value]);
  async function save() {
    if (v === value) return;
    try { await api.patchProfile(path, v); setErr(null); onSaved(); } catch (e) { setErr((e as Error).message); }
  }
  return (
    <label className="mb-2.5 block">
      <span className="label">{label}</span>
      {multiline
        ? <textarea className={`input ${err ? "border-bad" : ""}`} rows={3} value={v} onChange={(e) => setV(e.target.value)} onBlur={save} />
        : <input className={`input ${err ? "border-bad" : ""}`} value={v} onChange={(e) => setV(e.target.value)} onBlur={save} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />}
      {err && <span role="alert" className="mt-1 block text-[12px] text-bad">{err}</span>}
    </label>
  );
}

function Details({ data, onChange }: { data: ProfilePage; onChange: () => void }) {
  const p: Profile = data.profile;
  const [voice, setVoice] = useState(data.voice);
  const [importPath, setImportPath] = useState("");
  const [importErr, setImportErr] = useState<string | null>(null);
  return (
    <>
      <p className="mb-3 px-1 text-[12.5px] text-text-2">Everything here also edits on the page or through the chat. This is the full list, including things that are not on the CV.</p>
      {data.sections.map((spec) => <SectionEditor key={spec.key} spec={spec} items={p[spec.key]} onChange={onChange} />)}
      <section className="panel mb-2.5">
        <h2 className="mb-2 text-[14px] font-bold">What you are looking for</h2>
        <Field label="Keywords" path="search.keywords" value={`[${p.search.keywords.join(", ")}]`} onSaved={onChange} />
        <Field label="Locations" path="search.locations" value={`[${p.search.locations.join(", ")}]`} onSaved={onChange} />
        <div className="grid grid-cols-2 gap-x-3">
          <Field label="Start from" path="search.start_from" value={p.search.start_from} onSaved={onChange} />
          <Field label="Start until" path="search.start_to" value={p.search.start_to} onSaved={onChange} />
          <Field label="Weekly goal" path="preferences.weekly_goal" value={String(p.preferences.weekly_goal)} onSaved={onChange} />
        </div>
      </section>
      <section className="panel mb-2.5">
        <h2 className="mb-1 text-[14px] font-bold">Writing voice</h2>
        <textarea className="input" rows={5} value={voice} onChange={(e) => setVoice(e.target.value)} aria-label="Writing voice" />
        <button className="btn btn-sm mt-2" onClick={() => api.setVoice(voice)}>Save voice</button>
      </section>
      <section className="panel">
        <h2 className="mb-1 text-[14px] font-bold">Import</h2>
        <p className="mb-2 text-[12.5px] text-text-2">Replace the profile from a JobKiller <code>user_info</code> JSON. It comes in unverified.</p>
        <div className="flex gap-2">
          <input className="input" placeholder="~/JobKiller/resume_workspace/user_info/default_profile.json" value={importPath} onChange={(e) => setImportPath(e.target.value)} aria-label="Path to JSON" />
          <button className="btn" disabled={!importPath.trim()} onClick={() => api.importProfile(importPath).then(onChange).catch((e: Error) => setImportErr(e.message))}>Import</button>
        </div>
        <ErrorNote message={importErr} />
      </section>
    </>
  );
}
