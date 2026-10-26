import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api, STATUSES, type Status } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { ErrorNote, Score, STATUS_LABEL } from "../components/ui";

export default function JobDetail() {
  const { id } = useParams();
  const jobId = Number(id);
  const { refreshStats } = useStore();
  const { data, error, reload } = useLoad(() => api.job(jobId), [jobId]);
  const [notes, setNotes] = useState("");
  const [packBusy, setPackBusy] = useState(false);
  const [packError, setPackError] = useState<string | null>(null);

  if (error) return <div className="p-7"><Link to="/jobs" className="btn btn-quiet btn-sm mb-3"><ArrowLeft size={14} /> Jobs</Link><ErrorNote message={error} /></div>;
  if (!data) return <div className="p-7 text-text-2">Loading…</div>;
  const { job, dims, ats, pack, letter } = data;

  async function setStatus(s: Status) {
    await api.setStatus(job.id, s, notes || undefined);
    refreshStats();
    reload();
  }
  async function makePack() {
    setPackBusy(true);
    setPackError(null);
    try { await api.makePack(job.id); reload(); refreshStats(); } catch (e) { setPackError((e as Error).message); } finally { setPackBusy(false); }
  }

  return (
    <div className="p-7">
      <Link to="/jobs" className="btn btn-quiet btn-sm mb-3"><ArrowLeft size={14} /> Jobs</Link>
      <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <Score value={job.score} size="lg" />
          <div className="min-w-0">
            <h1 className="text-[24px] font-extrabold leading-tight">{job.title}</h1>
            <p className="text-text-2">{job.company}{job.location ? `, ${job.location}` : ""}{job.start_hint ? `. Starts ${job.start_hint}` : ""}{job.months ? `, ${job.months} months` : ""}{job.dutch_plus ? ". Dutch is a plus" : ""}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="status">Stage</label>
          <select id="status" className="input w-auto" value={job.status} onChange={(e) => setStatus(e.target.value as Status)}>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
          <input className="input w-48" placeholder="Note (saved with stage)" value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Note" />
          {job.url && <a className="btn" href={job.url} target="_blank" rel="noopener">Open posting <ExternalLink size={14} /></a>}
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          {dims && (
            <section className="panel">
              <h2 className="mb-3 text-[15px] font-bold">How you fit</h2>
              <ul className="mb-3 grid gap-1.5">
                {dims.map((d) => (
                  <li key={d.name} className="grid grid-cols-[150px_1fr_60px] items-center gap-3 text-[13px]">
                    <span>{d.name}</span>
                    <span className="h-1.5 overflow-hidden rounded bg-bg-3"><span className="block h-full bg-ok" style={{ width: `${Math.round((100 * d.value) / d.max)}%` }} /></span>
                    <span className="text-text-2">{d.value} / {d.max}</span>
                  </li>
                ))}
              </ul>
              <div className="grid gap-4 md:grid-cols-2">
                <div><h3 className="mb-1 text-[13px] font-bold text-text-2">Why</h3><ul className="list-disc pl-5">{job.reasons.map((r) => <li key={r}>{r}</li>)}</ul></div>
                <div><h3 className="mb-1 text-[13px] font-bold text-text-2">Gaps</h3>{job.gaps.length ? <ul className="list-disc pl-5 text-warn">{job.gaps.map((g) => <li key={g}>{g}</li>)}</ul> : <p className="text-text-2">Nothing obvious.</p>}</div>
              </div>
            </section>
          )}

          <section className="panel">
            <h2 className="mb-2 text-[15px] font-bold">ATS keywords {ats && <span className="ml-1 font-medium text-text-3">{ats.percent}% covered</span>}</h2>
            {ats ? (
              <>
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {ats.matched.map((k) => <span key={k} className="rounded-md border border-ok/40 px-2 py-0.5 text-[12.5px] text-ok">{k}</span>)}
                  {ats.missing.map((k) => <span key={k} className="rounded-md border border-bad/40 px-2 py-0.5 text-[12.5px] text-bad">{k}</span>)}
                </div>
                <p className="text-[12.5px] text-text-2">Green is in your CV{pack ? " (the tailored one)" : ""}; red is what the posting asks for and your CV does not mention. Add real evidence to your profile, never the word alone.</p>
              </>
            ) : <p className="text-text-2">Keywords appear once the job is scored.</p>}
          </section>

          <section className="panel border-line-2">
            <ErrorNote message={packError} />
            {pack ? (
              <>
                <h2 className="mb-2 text-[15px] font-bold">Your application pack</h2>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <a className="btn btn-primary" href={`/packs/${job.id}/cv.pdf`} target="_blank" rel="noopener">Open the CV (A4 PDF)</a>
                  {pack.apply_email && <a className="btn" href={`mailto:${pack.apply_email}`}>Email {pack.apply_email}</a>}
                  {job.status !== "applied" && <button className="btn" onClick={() => setStatus("applied")}>Mark as sent</button>}
                </div>
                <p className="mb-3 break-all text-[12px] text-text-3">{pack.dir}</p>
                {pack.change_summary.length > 0 && <><h3 className="mb-1 text-[13px] font-bold text-text-2">What changed in the CV</h3><ul className="mb-3 list-disc pl-5">{pack.change_summary.map((c) => <li key={c}>{c}</li>)}</ul></>}
                {letter && <><h3 className="mb-1 text-[13px] font-bold text-text-2">Cover letter</h3><pre className="whitespace-pre-wrap rounded-lg border border-line bg-bg-3 p-3 font-sans text-[13.5px]">{letter}</pre></>}
              </>
            ) : (
              <>
                <h2 className="mb-1 text-[15px] font-bold">Application pack</h2>
                <p className="mb-3 max-w-[60ch] text-text-2">A one-page CV reordered for this role and a cover letter in your voice, every claim checked against your profile.</p>
                <button className="btn btn-primary" onClick={makePack} disabled={packBusy}>{packBusy ? "Writing, about a minute…" : "Write CV + cover letter"}</button>
              </>
            )}
          </section>
        </div>

        <section className="panel xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:overflow-auto">
          <h2 className="mb-2 text-[15px] font-bold">The posting</h2>
          <pre className="whitespace-pre-wrap font-sans text-[13px] text-text-2">{job.description}</pre>
        </section>
      </div>
    </div>
  );
}
