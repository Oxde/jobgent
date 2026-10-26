import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Copy, X } from "lucide-react";
import { api, type ActionItem, type Funnel, type HomeData } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { Empty, ErrorNote, JobLink, PageHead, VerdictChip } from "../components/ui";
import { useToast } from "../components/Toast";

const KIND_TONE: Record<ActionItem["kind"], string> = {
  offer: "border-l-ok",
  interview_soon: "border-l-accent",
  send: "border-l-accent",
  make_pack: "border-l-line-2",
  follow_up: "border-l-warn",
};

export default function Home() {
  const { profileVersion, refreshStats } = useStore();
  const { data, error, reload } = useLoad(() => api.home(), [profileVersion]);
  if (error) return <div className="p-7"><ErrorNote message={error} /></div>;
  if (!data) return <div className="p-7 text-text-2">Loading…</div>;
  return <HomeView data={data} reload={() => { reload(); refreshStats(); }} />;
}

function HomeView({ data, reload }: { data: HomeData; reload: () => void }) {
  const done = data.checklist.filter((c) => c.done).length;
  return (
    <div className="p-7">
      <PageHead title={`Internship from ${data.start_from}`} sub={`${data.weeks_left} weeks left. ${data.stats.applied_this_week} of ${data.stats.goal} applications sent this week.`}>
        <Link className="btn" to="/jobs">Find jobs</Link>
      </PageHead>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section className="panel">
          <h2 className="mb-1 text-[15px] font-bold">Worth a look <span className="ml-1 font-medium text-text-3">{data.actions.length}</span></h2>
          <p className="mb-3 text-[12.5px] text-text-3">Most urgent first: offers, interviews, packs to send by deadline, saved jobs, follow-ups.</p>
          {data.actions.length === 0 && <Empty>All caught up. Save jobs in <Link className="underline" to="/jobs">Jobs</Link> and they show up here when they need you.</Empty>}
          <ul className="flex flex-col gap-2">
            {data.actions.map((a) => <ActionRow key={`${a.kind}-${a.job.id}`} item={a} reload={reload} />)}
          </ul>
        </section>

        <div className="flex flex-col gap-4">
          {data.funnel && <FunnelCard funnel={data.funnel} weekly={data.weekly} goal={data.stats.goal} />}
          <section className="panel">
            <h2 className="mb-3 text-[15px] font-bold">Your profile <span className="ml-1 font-medium text-text-3">{done} / {data.checklist.length}</span></h2>
            <ul className="mb-3">
              {data.checklist.map((c) => (
                <li key={c.label} className={`flex items-start gap-2.5 py-1 ${c.done ? "text-text" : "text-text-2"}`}>
                  <span className={`mt-[3px] h-4 w-4 shrink-0 rounded-full border ${c.done ? "border-ok bg-ok" : "border-line-2"}`} aria-hidden />
                  <span className="text-[13.5px]">{c.label}{!c.done && <span className="block text-[12px] text-text-3">{c.hint}</span>}</span>
                </li>
              ))}
            </ul>
            <Link className="btn btn-sm" to="/me">Edit profile and CV</Link>
          </section>
        </div>
      </div>
    </div>
  );
}

function ActionRow({ item, reload }: { item: ActionItem; reload: () => void }) {
  const nav = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<{ subject: string; body: string } | null>(null);
  const id = item.job.id;

  async function markSent() {
    await api.setStatus(id, "applied");
    toast.show(`Marked as sent: ${item.job.title}`, { tone: "ok", undo: async () => { await api.undoStatus(id); reload(); } });
    reload();
  }
  async function draftFollowup() {
    setBusy(true);
    try { setDraft(await api.followup(id)); } catch (e) { toast.show((e as Error).message, { tone: "error" }); } finally { setBusy(false); }
  }
  async function followupSent() {
    await api.followupSent(id);
    setDraft(null);
    toast.show("Follow-up logged", { tone: "ok" });
    reload();
  }

  return (
    <li className={`rounded-lg border border-line border-l-[3px] bg-bg-2 px-3 py-2.5 ${KIND_TONE[item.kind]}`}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <JobLink id={id} className="font-semibold">{item.job.title}</JobLink>
          <span className="text-text-2"> · {item.job.company}</span> <VerdictChip verdict={item.job.verdict} />
          <div className="text-[12.5px] text-text-2">{item.text}</div>
        </div>
        {item.kind === "make_pack" && <button className="btn btn-sm" onClick={() => nav(`/jobs/${id}`)}>Write the pack</button>}
        {item.kind === "send" && (
          <>
            <a className="btn btn-sm" href={`/packs/${id}/cv.pdf`} target="_blank" rel="noopener">CV</a>
            <button className="btn btn-sm" onClick={() => nav(`/jobs/${id}?tab=email`)}>Email</button>
            {item.job.url && <a className="btn btn-sm" href={item.job.url} target="_blank" rel="noopener">Apply</a>}
            <button className="btn btn-sm btn-primary" onClick={markSent}>Mark sent</button>
          </>
        )}
        {item.kind === "follow_up" && <button className="btn btn-sm" onClick={draftFollowup} disabled={busy}>{busy ? "Writing…" : "Draft follow-up"}</button>}
        {(item.kind === "offer" || item.kind === "interview_soon") && <button className="btn btn-sm" onClick={() => nav(`/jobs/${id}`)}>Open</button>}
      </div>
      {draft && (
        <div className="mt-3 rounded-lg border border-line-2 bg-bg-3 p-3">
          <div className="mb-2 flex items-center justify-between">
            <b className="text-[13px]">Follow-up draft</b>
            <button className="btn btn-quiet btn-sm" onClick={() => setDraft(null)} aria-label="Close"><X size={14} /></button>
          </div>
          <CopyLine label="Subject" text={draft.subject} />
          <pre className="mb-2 whitespace-pre-wrap rounded-md bg-bg p-2.5 font-sans text-[13.5px]">{draft.body}</pre>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-sm" onClick={() => navigator.clipboard.writeText(draft.body).then(() => toast.show("Body copied"))}><Copy size={13} /> Copy body</button>
            <button className="btn btn-sm btn-primary" onClick={followupSent}>I sent it</button>
          </div>
        </div>
      )}
    </li>
  );
}

function CopyLine({ label, text }: { label: string; text: string }) {
  const toast = useToast();
  return (
    <div className="mb-2 flex items-center gap-2 text-[13px]">
      <span className="text-text-3">{label}</span>
      <span className="min-w-0 flex-1 truncate">{text}</span>
      <button className="btn btn-quiet btn-sm" onClick={() => navigator.clipboard.writeText(text).then(() => toast.show(`${label} copied`))}><Copy size={13} /></button>
    </div>
  );
}

function FunnelCard({ funnel, weekly, goal }: { funnel: Funnel; weekly: { week_start: string; sent: number }[]; goal: number }) {
  const steps = [
    { label: "Sent", value: funnel.sent },
    { label: "Heard back", value: funnel.heard_back },
    { label: "Interview", value: funnel.interview },
    { label: "Offer", value: funnel.offer },
  ];
  const max = Math.max(1, ...weekly.map((w) => w.sent), goal);
  return (
    <section className="panel">
      <h2 className="mb-1 text-[15px] font-bold">Your funnel</h2>
      <p className="mb-3 text-[12.5px] text-text-3">{funnel.sent ? `${funnel.response_rate}% of sent applications got an answer.` : "Send your first application to start the funnel."}</p>
      <ul className="mb-4 grid gap-1.5">
        {steps.map((s, i) => {
          const prev = i === 0 ? s.value : steps[i - 1].value;
          const pct = funnel.sent ? Math.round((100 * s.value) / funnel.sent) : 0;
          return (
            <li key={s.label} className="grid grid-cols-[90px_1fr_70px] items-center gap-2 text-[13px]">
              <span className="text-text-2">{s.label}</span>
              <span className="h-2 overflow-hidden rounded bg-bg-3"><span className="block h-full rounded bg-accent" style={{ width: `${Math.max(pct, s.value ? 4 : 0)}%` }} /></span>
              <span className="text-right">{s.value}{i > 0 && prev ? <span className="text-text-3"> · {Math.round((100 * s.value) / prev)}%</span> : null}</span>
            </li>
          );
        })}
      </ul>
      <div className="text-[12px] text-text-3">Sent per week (last 8), goal {goal}</div>
      <svg viewBox={`0 0 ${weekly.length * 22} 60`} className="mt-1 h-16 w-full" role="img" aria-label="Applications sent per week">
        <line x1="0" x2={weekly.length * 22} y1={60 - (52 * goal) / max} y2={60 - (52 * goal) / max} className="stroke-line-2" strokeDasharray="3 3" />
        {weekly.map((w, i) => {
          const h = (52 * w.sent) / max;
          return <rect key={w.week_start} x={i * 22 + 4} y={60 - h} width={14} height={Math.max(h, 1)} rx={2} className={w.sent >= goal ? "fill-ok" : "fill-accent/70"}><title>{`Week of ${w.week_start}: ${w.sent}`}</title></rect>;
        })}
      </svg>
    </section>
  );
}
