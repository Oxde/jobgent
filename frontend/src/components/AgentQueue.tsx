import { useState } from "react";
import { Bot, Play } from "lucide-react";
import { api } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { Empty, ErrorNote, JobLink, Score, UrgencyTags, VerdictChip } from "./ui";
import { useToast } from "./Toast";

/** What the job agent recommends, with its reasons. The student decides; the agent never sends anything. */
export default function AgentQueue() {
  const { refreshStats } = useStore();
  const toast = useToast();
  const { data, error, reload } = useLoad(() => api.agent(), []);
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    try {
      const r = await api.agentRun();
      toast.show(`Agent: ${r.fetched} new postings, ${r.evaluated} evaluated, ${r.queued} worth a look`, { tone: "ok" });
      reload();
    } catch (e) { toast.show((e as Error).message, { tone: "error" }); } finally { setRunning(false); }
  }

  if (error) return <ErrorNote message={error} />;
  if (!data) return <p className="text-text-2">Loading…</p>;
  const last = data.last_run;
  return (
    <div className="flex flex-col gap-4">
      <section className="panel flex flex-wrap items-center gap-3">
        <Bot size={20} className="text-accent" aria-hidden />
        <div className="min-w-0 flex-1 text-[13.5px]">
          <b>The job agent</b> fetches new postings, scores them, evaluates the best new ones (checks, requirements, verdict) and lists here the ones worth your time. It never applies or sends anything.
          <div className="mt-0.5 text-[12.5px] text-text-3">
            {last ? `Last run ${new Date(last.started_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}: ${last.fetched} new, ${last.evaluated} evaluated, ${last.queued} queued${last.status === "failed" ? `, failed: ${last.error}` : ""}.` : "Not run yet."}
            {" "}Daily at 08:00: run <code>uv run jobgent agent --schedule 08:00</code> once for the setup.
          </div>
          {last?.note && <details className="mt-1 text-[12px] text-text-2"><summary className="cursor-pointer">Notes from the last run</summary><pre className="whitespace-pre-wrap font-sans">{last.note}</pre></details>}
        </div>
        <button className="btn btn-primary" onClick={run} disabled={running}><Play size={14} /> {running ? "Running, a few minutes…" : "Run now"}</button>
      </section>

      {data.queue.length === 0 && <Empty>Nothing queued. Run the agent, or lower the bar later in Settings.</Empty>}
      <ul className="flex flex-col gap-2">
        {data.queue.map((q) => (
          <li key={q.job.id} className="flex flex-wrap items-start gap-3 rounded-lg border border-line bg-bg-2 p-3">
            <JobLink id={q.job.id}><Score value={q.job.score} /></JobLink>
            <div className="min-w-0 flex-1">
              <JobLink id={q.job.id} className="font-semibold">{q.job.title}</JobLink>
              <span className="text-text-2"> · {q.job.company}</span>{" "}
              <span className="inline-flex gap-1 align-middle"><VerdictChip verdict={q.verdict} /><UrgencyTags deadline={q.job.deadline} ageDays={q.job.age_days} alsoIn={q.job.also_in} /></span>
              <p className="mt-0.5 text-[13px] text-text-2">{q.reason}</p>
              {q.red_flags.length > 0 && <p className="text-[12.5px] text-warn">Worth knowing: {q.red_flags.join(" · ")}</p>}
            </div>
            <div className="flex gap-1.5">
              <button className="btn btn-sm border-ok/50 text-ok" onClick={async () => { await api.setStatus(q.job.id, "liked"); refreshStats(); reload(); toast.show(`Saved: ${q.job.title}`, { undo: async () => { await api.undoStatus(q.job.id); reload(); } }); }}>Save</button>
              <button className="btn btn-quiet btn-sm" onClick={async () => { await api.agentDismiss(q.job.id); reload(); }}>Dismiss</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
