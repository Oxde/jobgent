import { useEffect, useRef, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { api, type JobSummary, type Profile } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { ErrorNote, PageHead } from "../components/ui";
import SectionEditor from "../components/SectionEditor";

/** One field of the profile, saved on blur or Enter. */
function Field({ label, path, value, multiline, onSaved }: { label: string; path: string; value: string; multiline?: boolean; onSaved: () => void }) {
  const [v, setV] = useState(value);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setV(value), [value]);
  async function save() {
    if (v === value) return;
    setState("saving");
    try { await api.patchProfile(path, v); setState("saved"); setErr(null); onSaved(); setTimeout(() => setState("idle"), 1200); } catch (e) { setState("error"); setErr((e as Error).message); }
  }
  const cls = `input ${state === "error" ? "border-bad" : ""}`;
  return (
    <label className="mb-2.5 block">
      <span className="label flex justify-between"><span>{label}</span><span className="text-text-3">{state === "saving" ? "Saving…" : state === "saved" ? "Saved" : ""}</span></span>
      {multiline
        ? <textarea className={cls} rows={3} value={v} onChange={(e) => setV(e.target.value)} onBlur={save} />
        : <input className={cls} value={v} onChange={(e) => setV(e.target.value)} onBlur={save} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />}
      {err && <span role="alert" className="mt-1 block text-[12px] text-bad">{err}</span>}
    </label>
  );
}

export default function Me() {
  const { profileVersion, bumpProfile } = useStore();
  const { data, error, reload } = useLoad(() => api.profile(), [profileVersion]);
  const { data: pipeline } = useLoad(() => api.applications(), [profileVersion]);
  const [template, setTemplate] = useState<string | null>(null);
  const [target, setTarget] = useState<number | "">("");
  const { data: targetPage } = useLoad(() => (target ? api.job(target) : Promise.resolve(null)), [target, profileVersion]);
  const [importPath, setImportPath] = useState("");
  const [importErr, setImportErr] = useState<string | null>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const [frameKey, setFrameKey] = useState(0);
  useEffect(() => setFrameKey((k) => k + 1), [profileVersion]);

  function changed() { reload(); bumpProfile(); }

  if (error) return <div className="p-7"><ErrorNote message={error} /></div>;
  if (!data) return <div className="p-7 text-text-2">Loading…</div>;
  const p: Profile = data.profile;
  const tid = template ?? p.preferences.template;
  const done = data.checklist.filter((c) => c.done).length;
  const targets: JobSummary[] = pipeline ? pipeline.flatMap((c) => c.cards.map((card) => card.job)) : [];
  const ats = targetPage?.ats ?? null;

  async function pickTemplate(id: string) {
    setTemplate(id);
    await api.patchProfile("preferences.template", id);
    bumpProfile();
  }
  async function doImport() {
    setImportErr(null);
    try { await api.importProfile(importPath); changed(); } catch (e) { setImportErr((e as Error).message); }
  }

  return (
    <div className="p-7">
      <PageHead title="Me" sub={`Your profile is the only thing the tool may say about you. ${done} of ${data.checklist.length} checks done.`}>
        <button className={`btn ${p.verified ? "" : "btn-primary"}`} onClick={() => api.patchProfile("verified", p.verified ? "false" : "true").then(changed)}>
          {p.verified ? "Verified ✓ (click to unverify)" : "Mark profile verified"}
        </button>
      </PageHead>

      <div className="grid gap-5 xl:grid-cols-[minmax(340px,440px)_minmax(0,1fr)]">
        <div className="min-w-0">
          <section className="panel mb-2.5">
            <h2 className="mb-2 text-[15px] font-bold">About you</h2>
            <Field label="Name" path="personal.name" value={p.personal.name} onSaved={changed} />
            <Field label="Headline (one line under your name)" path="personal.headline" value={p.personal.headline} onSaved={changed} />
            <Field label="Summary (2–3 sentences)" path="summary" value={p.summary} multiline onSaved={changed} />
            <div className="grid grid-cols-2 gap-x-3">
              <Field label="Email" path="personal.email" value={p.personal.email} onSaved={changed} />
              <Field label="Phone" path="personal.phone" value={p.personal.phone} onSaved={changed} />
              <Field label="Location" path="personal.location" value={p.personal.location} onSaved={changed} />
              <Field label="LinkedIn" path="personal.linkedin" value={p.personal.linkedin} onSaved={changed} />
              <Field label="GitHub" path="personal.github" value={p.personal.github} onSaved={changed} />
            </div>
          </section>

          {data.sections.map((spec) => (
            <SectionEditor key={spec.key} spec={spec} items={p[spec.key]} onChange={changed} />
          ))}

          <section className="panel mb-2.5">
            <h2 className="mb-2 text-[15px] font-bold">What you are looking for</h2>
            <Field label="Keywords (comma separated)" path="search.keywords" value={`[${p.search.keywords.join(", ")}]`} onSaved={changed} />
            <Field label="Locations" path="search.locations" value={`[${p.search.locations.join(", ")}]`} onSaved={changed} />
            <div className="grid grid-cols-2 gap-x-3">
              <Field label="Start from" path="search.start_from" value={p.search.start_from} onSaved={changed} />
              <Field label="Start until" path="search.start_to" value={p.search.start_to} onSaved={changed} />
              <Field label="Min months" path="search.months_min" value={String(p.search.months_min)} onSaved={changed} />
              <Field label="Max months" path="search.months_max" value={String(p.search.months_max)} onSaved={changed} />
              <Field label="Weekly goal" path="preferences.weekly_goal" value={String(p.preferences.weekly_goal)} onSaved={changed} />
            </div>
          </section>

          <section className="panel mb-2.5">
            <h2 className="mb-1 text-[15px] font-bold">Writing voice</h2>
            <p className="mb-2 text-[12.5px] text-text-2">How cover letters should sound.</p>
            <VoiceEditor initial={data.voice} />
          </section>

          <section className="panel">
            <h2 className="mb-1 text-[15px] font-bold">Import</h2>
            <p className="mb-2 text-[12.5px] text-text-2">Load a JobKiller <code>user_info</code> JSON. It replaces the profile and leaves it unverified so you can check it.</p>
            <div className="flex gap-2">
              <input className="input" placeholder="~/JobKiller/resume_workspace/user_info/default_profile.json" value={importPath} onChange={(e) => setImportPath(e.target.value)} aria-label="Path to JSON" />
              <button className="btn" onClick={doImport} disabled={!importPath.trim()}>Import</button>
            </div>
            <ErrorNote message={importErr} />
          </section>
        </div>

        <div className="min-w-0 xl:sticky xl:top-4 xl:self-start">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-[13px] text-text-2">Template
              <select className="input w-auto" value={tid} onChange={(e) => pickTemplate(e.target.value)}>
                {data.templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2 text-[13px] text-text-2">Check against
              <select className="input w-auto max-w-[260px]" value={target} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}>
                <option value="">no job</option>
                {targets.map((j) => <option key={j.id} value={j.id}>{j.title} · {j.company}</option>)}
              </select>
            </label>
            <button className="btn btn-quiet btn-sm" onClick={() => setFrameKey((k) => k + 1)} aria-label="Refresh preview"><RefreshCw size={14} /></button>
            <a className="btn btn-sm ml-auto" href={`/api/cv/preview?template=${tid}`} target="_blank" rel="noopener">Open full size <ExternalLink size={13} /></a>
          </div>
          {target !== "" && (
            <div className="mb-3 rounded-lg border border-line bg-bg-2 p-3">
              {ats ? (
                <>
                  <b className="text-[13px]">{ats.percent}% of the posting's keywords are in this CV</b>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {ats.matched.map((k) => <span key={k} className="rounded-md border border-ok/40 px-2 py-0.5 text-[12.5px] text-ok">{k}</span>)}
                    {ats.missing.map((k) => <span key={k} className="rounded-md border border-bad/40 px-2 py-0.5 text-[12.5px] text-bad">{k}</span>)}
                  </div>
                </>
              ) : <span className="text-[13px] text-text-2">No keywords for this job yet; it needs to be scored first.</span>}
            </div>
          )}
          <iframe key={frameKey} ref={frame} title="CV preview" src={`/api/cv/preview?template=${tid}`} className="h-[calc(100vh-150px)] w-full rounded-xl border border-line-2 bg-white" />
        </div>
      </div>
    </div>
  );
}

function VoiceEditor({ initial }: { initial: string }) {
  const [text, setText] = useState(initial);
  const [state, setState] = useState("");
  useEffect(() => setText(initial), [initial]);
  return (
    <>
      <textarea className="input" rows={6} value={text} onChange={(e) => setText(e.target.value)} aria-label="Writing voice" />
      <div className="mt-2 flex items-center gap-2">
        <button className="btn btn-sm" onClick={() => api.setVoice(text).then(() => { setState("Saved"); setTimeout(() => setState(""), 1200); })}>Save voice</button>
        <span className="text-[12px] text-text-3">{state}</span>
      </div>
    </>
  );
}
