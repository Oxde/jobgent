import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, STATUSES, type JobSummary, type Status } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { Empty, ErrorNote, JobLink, PageHead, Score, STATUS_LABEL, StatusTag, UrgencyTags, VerdictChip } from "../components/ui";
import { useToast } from "../components/Toast";
import Pipeline from "../components/Pipeline";
import AgentQueue from "../components/AgentQueue";

export default function Jobs() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("view");
  const view: "find" | "agent" | "pipeline" = raw === "pipeline" || raw === "agent" ? raw : "find";
  return (
    <div className="p-7">
      <PageHead title="Jobs" sub={{ find: "Internships in the Netherlands, in English, scored against your profile.", agent: "What the job agent recommends, and why.", pipeline: "Everything you saved or sent. Drag a card to move it." }[view]}>
        <div className="inline-flex overflow-hidden rounded-lg border border-line-2" role="tablist">
          {(["find", "agent", "pipeline"] as const).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} className={`min-h-[36px] px-4 text-[13.5px] font-medium ${view === v ? "bg-bg-3 text-text" : "text-text-2 hover:text-text"}`} onClick={() => setParams(v === "find" ? {} : { view: v })}>
              {{ find: "Find", agent: "Agent picks", pipeline: "Pipeline" }[v]}
            </button>
          ))}
        </div>
      </PageHead>
      {view === "find" ? <Find /> : view === "agent" ? <AgentQueue /> : <Pipeline />}
    </div>
  );
}

function Find() {
  const { refreshStats } = useStore();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [status, setStatus] = useState("");
  const { data, error, reload } = useLoad(() => api.jobs({ q, min_score: minScore, status }), [q, minScore, status]);

  async function decide(job: JobSummary, s: Status) {
    await api.setStatus(job.id, s);
    refreshStats();
    reload();
    toast.show(s === "skipped" ? `Skipped: ${job.title}` : `Saved: ${job.title}`, { undo: async () => { await api.undoStatus(job.id); reload(); refreshStats(); } });
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="min-w-[240px] flex-1"><span className="label">Search</span><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Title or company" /></label>
        <label><span className="label">Score at least</span><input className="input w-24" type="number" min={0} max={100} value={minScore} onChange={(e) => setMinScore(Number(e.target.value) || 0)} /></label>
        <label><span className="label">Status</span>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Any</option>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
        </label>
      </div>
      <ErrorNote message={error} />
      {data && data.length === 0 && <Empty>No scored internships yet. Run <code>jobgent fetch</code> with your Anthropic key set, or paste a posting link to the assistant.</Empty>}
      {data && data.length > 0 && (
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-left text-[12px] text-text-3">
              <th className="pb-2 pl-2 font-medium">Match</th><th className="pb-2 font-medium">Role</th><th className="pb-2 font-medium">Company</th><th className="pb-2 font-medium">Location</th><th className="pb-2 font-medium">Posted</th><th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {data.map((j) => (
              <tr key={j.id} className="border-t border-line">
                <td className="py-2 pl-2 pr-3"><JobLink id={j.id}><Score value={j.score} /></JobLink></td>
                <td className="py-2 pr-3">
                  <JobLink id={j.id} className="font-semibold text-[14.5px]">{j.title}</JobLink>
                  <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle"><VerdictChip verdict={j.verdict} /><StatusTag status={j.status} /><UrgencyTags deadline={j.deadline} ageDays={j.age_days} alsoIn={j.also_in} /></span>
                </td>
                <td className="py-2 pr-3">{j.company}</td>
                <td className="py-2 pr-3 text-text-2">{j.location ?? ""}</td>
                <td className="py-2 pr-3 text-text-2">{j.posted_at ? new Date(j.posted_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : ""}</td>
                <td className="py-2 pr-2">
                  <div className="flex justify-end gap-1.5">
                    <button className="btn btn-sm border-ok/50 text-ok" disabled={j.status !== "new"} onClick={() => decide(j, "liked")}>Save</button>
                    <button className="btn btn-sm btn-quiet" onClick={() => decide(j, "skipped")}>Skip</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
