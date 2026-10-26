import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Status } from "../lib/api";

export function Score({ value, size = "md" }: { value: number | null; size?: "md" | "lg" }) {
  const band = value === null ? "none" : value >= 70 ? "hi" : value >= 50 ? "mid" : "lo";
  const cls = { none: "border-line-2 text-text-3", hi: "border-ok text-ok bg-ok/10", mid: "border-warn text-warn bg-warn/10", lo: "border-line-2 text-text-3" }[band];
  const dim = size === "lg" ? "h-16 w-16 text-[24px]" : "h-11 w-11 text-[16px]";
  return <span className={`inline-grid shrink-0 place-items-center rounded-lg border bg-bg-3 font-display font-extrabold ${dim} ${cls}`} aria-label={value === null ? "Not scored" : `Match ${value}`}>{value ?? "–"}</span>;
}

export const STATUS_LABEL: Record<Status, string> = { new: "New", liked: "Saved", pack_ready: "Pack ready", applied: "Applied", interview: "Interviewing", offer: "Offer", rejected: "Rejected", skipped: "Skipped" };

export function StatusTag({ status }: { status: Status }) {
  if (status === "new") return null;
  const tone = status === "applied" || status === "interview" || status === "offer" ? "text-ok bg-ok/10" : status === "liked" || status === "pack_ready" ? "text-accent bg-accent/10" : "text-text-2 bg-bg-3";
  return <span className={`tag ${tone}`}>{STATUS_LABEL[status]}</span>;
}

export function PageHead({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[24px] font-extrabold">{title}</h1>
        {sub && <p className="mt-0.5 text-text-2">{sub}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="max-w-[56ch] py-8 text-text-2">{children}</p>;
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-[13px] text-bad">{message}</p>;
}

export function JobLink({ id, children, className = "" }: { id: number; children: ReactNode; className?: string }) {
  return <Link to={`/jobs/${id}`} className={`hover:underline ${className}`}>{children}</Link>;
}

export function VerdictChip({ verdict }: { verdict: "apply" | "consider" | "skip" | null }) {
  if (!verdict) return null;
  const style = { apply: "text-ok bg-ok/10 border-ok/40", consider: "text-warn bg-warn/10 border-warn/40", skip: "text-text-3 bg-bg-3 border-line-2" }[verdict];
  const label = { apply: "Apply", consider: "Consider", skip: "Skip" }[verdict];
  return <span className={`inline-block rounded-md border px-2 py-0.5 text-[11.5px] font-semibold ${style}`}>{label}</span>;
}

export function daysUntil(deadline: string | null): number | null {
  if (!deadline) return null;
  const d = new Date(deadline);
  if (Number.isNaN(d.getTime())) return null;
  return Math.ceil((d.getTime() - Date.now()) / 86400000);
}

export function UrgencyTags({ deadline, ageDays, alsoIn }: { deadline: string | null; ageDays: number | null; alsoIn?: number }) {
  const left = daysUntil(deadline);
  return (
    <>
      {left !== null && left >= 0 && left <= 7 && <span className="tag bg-bad/10 text-bad" title={`Deadline ${deadline}`}>🔥 {left === 0 ? "closes today" : `${left}d left`}</span>}
      {ageDays !== null && ageDays > 30 && <span className="tag bg-warn/10 text-warn" title="Posted more than 30 days ago; may be filled">⚠ {ageDays}d old</span>}
      {alsoIn ? <span className="tag" title="Same posting in other cities">+{alsoIn} {alsoIn === 1 ? "city" : "cities"}</span> : null}
    </>
  );
}
