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
