import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Copy, ExternalLink, ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import { api, STATUSES, type DocKind, type DocumentView, type EvaluationView, type InterviewPrep, type Status, type TimelineItem } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { ErrorNote, Score, STATUS_LABEL, UrgencyTags, VerdictChip } from "../components/ui";
import CvCanvas from "../components/CvCanvas";
import DocEditor from "../components/DocEditor";
import { useToast } from "../components/Toast";

type Tab = "resume" | "letter" | "email" | "interview" | "posting" | "notes";
const TABS: [Tab, string][] = [["resume", "Resume"], ["letter", "Cover letter"], ["email", "Email"], ["interview", "Interview"], ["posting", "Posting"], ["notes", "Notes"]];

export default function JobDetail() {
  const { id } = useParams();
  const jobId = Number(id);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "resume";
  const { refreshStats } = useStore();
  const toast = useToast();
  const { data, error, reload } = useLoad(() => api.job(jobId), [jobId]);
  const docs = useLoad(() => api.documents(jobId), [jobId]);
  const [docVersion, setDocVersion] = useState(0);
  const [busy, setBusy] = useState<"" | "evaluate" | "pack">("");
  const [askInterview, setAskInterview] = useState(false);

  if (error) return <div className="p-7"><Link to="/jobs" className="btn btn-quiet btn-sm mb-3"><ArrowLeft size={14} /> Jobs</Link><ErrorNote message={error} /></div>;
  if (!data) return <div className="p-7 text-text-2">Loading…</div>;
  const { job, pack, evaluation } = data;

  function refreshDocs() { docs.reload(); setDocVersion((v) => v + 1); reload(); }

  async function setStatus(s: Status) {
    await api.setStatus(job.id, s);
    refreshStats(); reload();
    toast.show(`Moved to ${STATUS_LABEL[s]}`, { undo: async () => { await api.undoStatus(job.id); reload(); refreshStats(); } });
    if (s === "interview") setAskInterview(true);
  }
  async function evaluate() {
    setBusy("evaluate");
    try { await api.evaluate(job.id); reload(); } catch (e) { toast.show((e as Error).message, { tone: "error" }); } finally { setBusy(""); }
  }
  async function makePack() {
    setBusy("pack");
    try { await api.makePack(job.id); refreshDocs(); refreshStats(); toast.show("Pack written: CV, cover letter and email", { tone: "ok" }); }
    catch (e) { toast.show((e as Error).message, { tone: "error" }); } finally { setBusy(""); }
  }

  return (
    <div className="p-6">
      <Link to="/jobs" className="btn btn-quiet btn-sm mb-2"><ArrowLeft size={14} /> Jobs</Link>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <Score value={job.score} size="lg" />
          <div className="min-w-0">
            <h1 className="text-[23px] font-extrabold leading-tight">{job.title}</h1>
            <p className="text-text-2">{job.company}{job.location ? `, ${job.location}` : ""}{job.start_hint ? `. Starts ${job.start_hint}` : ""}{job.months ? `, ${job.months} months` : ""}</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5"><VerdictChip verdict={evaluation?.verdict ?? job.verdict} /><UrgencyTags deadline={evaluation?.deadline ?? job.deadline} ageDays={job.age_days} /></div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="input w-auto" value={job.status} onChange={(e) => setStatus(e.target.value as Status)} aria-label="Stage">
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
          {job.url && <a className="btn" href={job.url} target="_blank" rel="noopener">Open posting <ExternalLink size={14} /></a>}
        </div>
      </header>
      {askInterview && <InterviewPrompt jobId={job.id} onDone={() => { setAskInterview(false); reload(); }} />}

      <div className="grid gap-5 xl:grid-cols-[minmax(340px,440px)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <EvaluationPanel evaluation={evaluation} busy={busy === "evaluate"} onEvaluate={evaluate} />
          <section className="panel border-line-2">
            {pack ? (
              <>
                <h2 className="mb-2 text-[15px] font-bold">Application pack</h2>
                <div className="mb-2 flex flex-wrap gap-2">
                  <a className="btn btn-sm btn-primary" href={`/packs/${job.id}/cv.pdf`} target="_blank" rel="noopener">CV (A4 PDF)</a>
                  <button className="btn btn-sm" onClick={() => setParams({ tab: "email" })}>Email</button>
                  {job.status !== "applied" && <button className="btn btn-sm" onClick={() => setStatus("applied")}>Mark as sent</button>}
                  <button className="btn btn-quiet btn-sm" disabled={busy === "pack"} onClick={makePack}>{busy === "pack" ? "Rewriting…" : "Rewrite pack"}</button>
                </div>
                <AtsReport ok={pack.ats_ok} problems={pack.ats_problems} keywords={pack.keywords} checkThis={pack.check_this} />
                {Object.keys(pack.review_notes).length > 0 && (
                  <details className="mt-2 text-[12.5px]"><summary className="cursor-pointer text-text-2">Reviewer notes</summary>
                    <ul className="mt-1 list-disc pl-5 text-text-2">{Object.entries(pack.review_notes).map(([k, v]) => <li key={k}><b className="capitalize">{k.replace("_", " ")}:</b> {v}</li>)}</ul>
                  </details>
                )}
              </>
            ) : (
              <>
                <h2 className="mb-1 text-[15px] font-bold">Application pack</h2>
                <p className="mb-3 text-[13px] text-text-2">A one-page CV for this role and a cover letter in your voice. A second agent reviews both; every number is checked against your profile.</p>
                <button className="btn btn-primary" onClick={makePack} disabled={busy === "pack"}>{busy === "pack" ? "Writing, about a minute…" : "Write CV + cover letter"}</button>
              </>
            )}
          </section>
        </div>

        <section className="flex min-w-0 flex-col">
          <div className="mb-3 flex flex-wrap gap-1 border-b border-line" role="tablist">
            {TABS.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} onClick={() => setParams({ tab: k })}
                className={`-mb-px min-h-[38px] border-b-2 px-3 text-[13.5px] font-medium ${tab === k ? "border-accent text-text" : "border-transparent text-text-2 hover:text-text"}`}>{label}</button>
            ))}
          </div>
          {tab === "resume" && (
            <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              {docs.data?.cv ? <DocEditor jobId={job.id} kind="cv" doc={docs.data.cv} onChange={refreshDocs} /> : <p className="text-[13px] text-text-2">Your general CV is shown. Write the pack to get a version tailored to this posting, editable piece by piece here.</p>}
              <CvCanvas template="" editable={false} src={`/api/jobs/${job.id}/cv?v=${docVersion}`} />
            </div>
          )}
          {tab === "letter" && <DocTab jobId={job.id} kind="letter" doc={docs.data?.letter ?? null} onChange={refreshDocs} empty="No cover letter yet. Write the pack first." />}
          {tab === "email" && <EmailTab jobId={job.id} doc={docs.data?.email ?? null} pack={!!pack} applyEmail={pack?.apply_email ?? null} onChange={refreshDocs} />}
          {tab === "posting" && (
            <div className="panel">
              {job.url && <a className="btn btn-sm mb-3" href={job.url} target="_blank" rel="noopener">Open the original <ExternalLink size={13} /></a>}
              <pre className="whitespace-pre-wrap font-sans text-[13px] text-text-2">{job.description}</pre>
            </div>
          )}
          {tab === "notes" && <NotesTab jobId={job.id} />}
          {tab === "interview" && <InterviewTab jobId={job.id} />}
        </section>
      </div>
    </div>
  );
}

function EvaluationPanel({ evaluation, busy, onEvaluate }: { evaluation: EvaluationView | null; busy: boolean; onEvaluate: () => void }) {
  if (!evaluation) {
    return (
      <section className="panel">
        <h2 className="mb-1 text-[15px] font-bold">Should you apply?</h2>
        <p className="mb-3 text-[13px] text-text-2">Checks the posting is still open, runs the checks (Dutch, location, work rights, red flags) and matches every requirement against your profile.</p>
        <button className="btn" onClick={onEvaluate} disabled={busy}>{busy ? "Evaluating…" : "Evaluate this job"}</button>
      </section>
    );
  }
  const icon = { pass: <ShieldCheck size={14} className="text-ok" />, flag: <ShieldAlert size={14} className="text-warn" />, fail: <ShieldX size={14} className="text-bad" /> };
  const mark = { covered: { s: "✓", c: "text-ok" }, partial: { s: "~", c: "text-warn" }, gap: { s: "–", c: "text-bad" } };
  return (
    <section className="panel">
      <div className="mb-2 flex items-center gap-2"><h2 className="text-[15px] font-bold">Should you apply?</h2><VerdictChip verdict={evaluation.verdict} /><button className="btn btn-quiet btn-sm ml-auto" onClick={onEvaluate} disabled={busy}>{busy ? "…" : "Re-check"}</button></div>
      <p className="mb-3 text-[13.5px]">{evaluation.verdict_reason}</p>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {evaluation.gates.map((g) => (
          <span key={g.name} title={g.reason} className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[12px] ${g.status === "pass" ? "border-line text-text-2" : g.status === "flag" ? "border-warn/40 text-warn" : "border-bad/40 text-bad"}`}>
            {icon[g.status]} {g.name.replace("_", " ")}
          </span>
        ))}
      </div>
      {evaluation.requirements.length > 0 && (
        <>
          <div className="mb-1 flex justify-between text-[12px] text-text-3"><span>Requirement → your evidence</span><span>{evaluation.coverage}% covered</span></div>
          <ul className="divide-y divide-line rounded-lg border border-line">
            {evaluation.requirements.map((r) => (
              <li key={r.text} className="grid grid-cols-[18px_1fr] gap-2 px-2.5 py-1.5 text-[13px]">
                <span className={`font-bold ${mark[r.status].c}`} aria-label={r.status}>{mark[r.status].s}</span>
                <span>
                  {r.text} <span className="text-[11px] text-text-3">{r.importance}{r.basis === "inferred" ? ", inferred" : ""}</span>
                  {r.evidence && <span className="block text-[12px] text-text-2">{r.evidence}</span>}
                  {r.status === "gap" && r.importance === "critical" && <span className="block text-[12px] text-bad">Must-have you don't show yet: address it honestly in the letter.</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function AtsReport({ ok, problems, keywords, checkThis }: { ok: boolean; problems: string[]; keywords: Record<string, string[]>; checkThis: string[] }) {
  const chip = (k: string, cls: string) => <span key={k} className={`rounded-md border px-2 py-0.5 text-[12px] ${cls}`}>{k}</span>;
  return (
    <div className="flex flex-col gap-2 text-[12.5px]">
      <div className={ok ? "text-ok" : "text-warn"}>{ok ? "ATS check passed: an applicant tracking system can read your PDF." : "ATS check:"}</div>
      {problems.length > 0 && <ul className="list-disc pl-5 text-warn">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
      {keywords.covered?.length || keywords.missing_but_in_profile?.length || keywords.gap?.length ? (
        <div className="flex flex-wrap gap-1.5">
          {(keywords.covered ?? []).map((k) => chip(k, "border-ok/40 text-ok"))}
          {(keywords.missing_but_in_profile ?? []).map((k) => chip(k + " (you have it)", "border-warn/40 text-warn"))}
          {(keywords.gap ?? []).map((k) => chip(k, "border-bad/40 text-bad"))}
        </div>
      ) : null}
      {checkThis.length > 0 && <div className="text-text-2">Check these names, the fact guard did not find them in your profile: <b>{checkThis.join(", ")}</b></div>}
    </div>
  );
}

function DocTab({ jobId, kind, doc, onChange, empty }: { jobId: number; kind: DocKind; doc: DocumentView | null; onChange: () => void; empty: string }) {
  if (!doc) return <p className="text-[13px] text-text-2">{empty}</p>;
  return <DocEditor jobId={jobId} kind={kind} doc={doc} onChange={onChange} />;
}

function EmailTab({ jobId, doc, pack, applyEmail, onChange }: { jobId: number; doc: DocumentView | null; pack: boolean; applyEmail: string | null; onChange: () => void }) {
  const toast = useToast();
  if (!doc) return <p className="text-[13px] text-text-2">The email appears once the pack is written.</p>;
  const subject = doc.units.find((u) => u.id === "subject")?.text ?? "";
  const body = doc.units.find((u) => u.id === "body")?.text ?? "";
  const copy = (label: string, t: string) => navigator.clipboard.writeText(t).then(() => toast.show(`${label} copied`));
  return (
    <div className="flex flex-col gap-3">
      <div className="panel flex flex-wrap items-center gap-2 text-[13px]">
        <span className="text-text-3">To</span><b>{applyEmail ?? "Not in the posting: apply on their site, or add the address."}</b>
        <div className="ml-auto flex gap-2">
          <button className="btn btn-sm" onClick={() => copy("Subject", subject)}><Copy size={13} /> Subject</button>
          <button className="btn btn-sm" onClick={() => copy("Body", body)}><Copy size={13} /> Body</button>
          {applyEmail && <a className="btn btn-sm btn-primary" href={`mailto:${applyEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`}>Open in mail app</a>}
        </div>
      </div>
      {pack && <div className="text-[12.5px] text-text-2">Attach: <a className="underline" href={`/packs/${jobId}/cv.pdf`} target="_blank" rel="noopener">CV (PDF)</a> and the cover letter (copy it from its tab, or paste it in the email).</div>}
      <DocEditor jobId={jobId} kind="email" doc={doc} onChange={onChange} />
    </div>
  );
}

function NotesTab({ jobId }: { jobId: number }) {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [text, setText] = useState("");
  useEffect(() => { api.timeline(jobId).then(setItems).catch(() => setItems([])); }, [jobId]);
  return (
    <div className="flex flex-col gap-3">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) api.addNote(jobId, text).then((t) => { setItems(t); setText(""); }); }}>
        <input className="input" placeholder="Add a note: who you spoke to, what they asked, next steps" value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn">Add</button>
      </form>
      <p className="text-[12px] text-text-3">Notes stay on this computer and are never sent to the AI.</p>
      <ol className="relative border-l border-line pl-4">
        {items.length === 0 && <li className="text-[13px] text-text-2">Nothing yet. Status changes and your notes appear here.</li>}
        {[...items].reverse().map((i, k) => (
          <li key={k} className="mb-3">
            <span className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ${i.kind === "note" ? "bg-accent" : i.kind === "interview" ? "bg-ok" : "bg-line-2"}`} aria-hidden />
            <div className="text-[12px] text-text-3">{new Date(i.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
            <div className="text-[13.5px]">{i.text}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function InterviewPrompt({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const [at, setAt] = useState("");
  const toast = useToast();
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-ok/40 bg-ok/10 p-3 text-[13.5px]">
      <b>An interview, well done.</b> When is it?
      <input type="datetime-local" className="input w-auto" value={at} onChange={(e) => setAt(e.target.value)} aria-label="Interview date and time" />
      <button className="btn btn-sm btn-primary" disabled={!at} onClick={() => api.setInterview(jobId, at.length === 16 ? `${at}:00` : at).then(() => { toast.show("Interview saved", { tone: "ok" }); onDone(); })}>Save</button>
      <button className="btn btn-quiet btn-sm" onClick={onDone}>Later</button>
    </div>
  );
}

function InterviewTab({ jobId }: { jobId: number }) {
  const toast = useToast();
  const [prep, setPrep] = useState<InterviewPrep | null>(null);
  const [stage, setStage] = useState("first round");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.interviewPrep(jobId).then(setPrep).catch(() => setPrep(null)); }, [jobId]);
  async function make() {
    setBusy(true);
    try { setPrep(await api.makeInterviewPrep(jobId, stage)); } catch (e) { toast.show((e as Error).message, { tone: "error" }); } finally { setBusy(false); }
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="panel flex flex-wrap items-center gap-2 text-[13.5px]">
        <span>Prepare for the</span>
        <select className="input w-auto" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Interview stage">
          {["first round", "recruiter call", "technical interview", "case / assignment review", "final round"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="btn btn-primary" onClick={make} disabled={busy}>{busy ? "Preparing…" : prep ? "Prepare again" : "Prepare"}</button>
        <span className="text-[12px] text-text-3">Built from your profile and the CV and letter you sent. Stories never get invented numbers.</span>
      </div>
      {prep && (
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="panel">
            <h2 className="mb-2 text-[15px] font-bold">Likely questions <span className="text-[12px] font-normal text-text-3">({prep.stage})</span></h2>
            <ol className="list-decimal pl-5 text-[13.5px]">{prep.likely_questions.map((q) => <li key={q.question} className="mb-2"><b>{q.question}</b>{q.why && <span className="block text-[12px] text-text-3">Why: {q.why}</span>}{q.answer_hint && <span className="block text-[12.5px] text-text-2">Use: {q.answer_hint}</span>}</li>)}</ol>
          </section>
          <section className="panel">
            <h2 className="mb-2 text-[15px] font-bold">Your STAR stories</h2>
            {prep.stories.map((s) => (
              <details key={s.title} className="mb-2 rounded-lg border border-line p-2.5 text-[13px]" open>
                <summary className="cursor-pointer font-semibold">{s.title} <span className="text-[11.5px] font-normal text-text-3">{s.source}</span></summary>
                <dl className="mt-1 grid grid-cols-[80px_1fr] gap-x-2 gap-y-1">
                  <dt className="text-text-3">Situation</dt><dd>{s.situation}</dd><dt className="text-text-3">Task</dt><dd>{s.task}</dd>
                  <dt className="text-text-3">Action</dt><dd>{s.action}</dd><dt className="text-text-3">Result</dt><dd>{s.result}</dd>
                </dl>
              </details>
            ))}
          </section>
          <section className="panel">
            <h2 className="mb-2 text-[15px] font-bold">Stay consistent with what you sent</h2>
            <ul className="list-disc pl-5 text-[13.5px]">{prep.consistency.map((c) => <li key={c}>{c}</li>)}</ul>
            {prep.gaps_to_prepare.length > 0 && <><h3 className="mb-1 mt-3 text-[13px] font-bold text-text-2">Gaps to talk about honestly</h3><ul className="list-disc pl-5 text-[13.5px] text-warn">{prep.gaps_to_prepare.map((g) => <li key={g}>{g}</li>)}</ul></>}
          </section>
          <section className="panel">
            <h2 className="mb-2 text-[15px] font-bold">Questions to ask them</h2>
            <ul className="list-disc pl-5 text-[13.5px]">{prep.questions_to_ask.map((q) => <li key={q}>{q}</li>)}</ul>
          </section>
        </div>
      )}
    </div>
  );
}
