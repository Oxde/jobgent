import { Link, useNavigate } from "react-router-dom";
import { api, type ActionItem } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { Empty, ErrorNote, JobLink, PageHead } from "../components/ui";

const KIND_LABEL: Record<ActionItem["kind"], string> = { send: "Pack ready, not sent", make_pack: "Saved, no pack yet", follow_up: "No answer, follow up" };

export default function Home() {
  const { profileVersion, refreshStats } = useStore();
  const nav = useNavigate();
  const { data, error, reload } = useLoad(() => api.home(), [profileVersion]);
  if (error) return <div className="p-7"><ErrorNote message={error} /></div>;
  if (!data) return <div className="p-7 text-text-2">Loading…</div>;
  const done = data.checklist.filter((c) => c.done).length;

  async function markSent(id: number) {
    await api.setStatus(id, "applied");
    refreshStats();
    reload();
  }

  return (
    <div className="p-7">
      <PageHead title={`Internship from ${data.start_from}`} sub={`${data.weeks_left} weeks left. ${data.stats.applied_this_week} of ${data.stats.goal} applications sent this week.`}>
        <Link className="btn" to="/jobs">Find jobs</Link>
      </PageHead>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section className="panel">
          <h2 className="mb-3 text-[15px] font-bold">Needs you <span className="ml-1 text-text-3 font-medium">{data.actions.length}</span></h2>
          {data.actions.length === 0 && <Empty>Nothing waiting. Save jobs in <Link className="underline" to="/jobs">Jobs</Link> and they show up here as they need you.</Empty>}
          <ul className="divide-y divide-line">
            {data.actions.map((a) => (
              <li key={`${a.kind}-${a.job.id}`} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <JobLink id={a.job.id} className="font-semibold">{a.job.title}</JobLink>
                  <span className="text-text-2"> · {a.job.company}</span>
                  <div className="text-[12.5px] text-text-2">{KIND_LABEL[a.kind]}{a.days_since !== null ? ` (${a.days_since} days)` : ""}</div>
                </div>
                {a.kind === "make_pack" && <button className="btn btn-sm" onClick={() => nav(`/jobs/${a.job.id}`)}>Write the pack</button>}
                {a.kind === "send" && (
                  <>
                    <a className="btn btn-sm" href={`/packs/${a.job.id}/cv.pdf`} target="_blank" rel="noopener">CV</a>
                    {a.job.url && <a className="btn btn-sm" href={a.job.url} target="_blank" rel="noopener">Apply</a>}
                    <button className="btn btn-sm btn-primary" onClick={() => markSent(a.job.id)}>Mark sent</button>
                  </>
                )}
                {a.kind === "follow_up" && a.job.url && <a className="btn btn-sm" href={a.job.url} target="_blank" rel="noopener">Open posting</a>}
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2 className="mb-3 text-[15px] font-bold">Your profile <span className="ml-1 text-text-3 font-medium">{done} / {data.checklist.length}</span></h2>
          <ul className="mb-3">
            {data.checklist.map((c) => (
              <li key={c.label} className={`flex items-start gap-2.5 py-1.5 ${c.done ? "text-text" : "text-text-2"}`}>
                <span className={`mt-[3px] h-4 w-4 shrink-0 rounded-full border ${c.done ? "border-ok bg-ok" : "border-line-2"}`} aria-hidden />
                <span>{c.label}{!c.done && <span className="block text-[12px] text-text-3">{c.hint}</span>}</span>
              </li>
            ))}
          </ul>
          <Link className="btn btn-sm" to="/me">Edit profile and CV</Link>
        </section>
      </div>
    </div>
  );
}
