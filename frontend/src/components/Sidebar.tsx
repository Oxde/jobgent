import { NavLink } from "react-router-dom";
import { Briefcase, House, MessageSquare, Settings as SettingsIcon, UserRound } from "lucide-react";
import { useStore } from "../lib/store";

const items = [
  { to: "/", label: "Home", icon: House, end: true },
  { to: "/jobs", label: "Jobs", icon: Briefcase, end: false },
  { to: "/me", label: "Me", icon: UserRound, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
];

export default function Sidebar() {
  const { stats, chatOpen, setChatOpen } = useStore();
  const goal = stats?.goal ?? 0;
  const sent = stats?.applied_this_week ?? 0;
  const pct = goal ? Math.min(100, (100 * sent) / goal) : 0;
  const dash = 94.2;
  return (
    <aside className="flex h-full flex-col border-r border-line bg-bg-2 px-3 py-4">
      <div className="px-3 pb-5 font-display text-[20px] font-extrabold tracking-tight">Jobgent</div>
      <nav className="flex flex-col gap-0.5">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex min-h-[40px] items-center gap-2.5 rounded-lg px-3 text-[14px] font-medium ${isActive ? "bg-bg-3 text-text shadow-[inset_3px_0_0_var(--color-accent)]" : "text-text-2 hover:bg-bg-3 hover:text-text"}`
            }
          >
            <Icon size={17} strokeWidth={2} aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-2">
        <NavLink to="/jobs?view=pipeline" className="flex items-center gap-3 rounded-lg bg-bg-3 px-3 py-2.5 text-text-2" title="Applications sent this week against your goal">
          <svg viewBox="0 0 36 36" className="h-9 w-9 shrink-0" aria-hidden>
            <circle cx="18" cy="18" r="15" fill="none" strokeWidth="4" className="stroke-line-2" />
            <circle cx="18" cy="18" r="15" fill="none" strokeWidth="4" strokeLinecap="round" className="stroke-accent" strokeDasharray={dash} strokeDashoffset={dash - (dash * pct) / 100} style={{ transform: "rotate(-90deg)", transformOrigin: "50% 50%", transition: "stroke-dashoffset .4s ease" }} />
          </svg>
          <span className="leading-tight">
            <b className="block font-display text-[15px] text-text">{sent} / {goal}</b>
            <small className="text-[11.5px]">sent this week</small>
          </span>
        </NavLink>
        <button type="button" onClick={() => setChatOpen(!chatOpen)} className={`btn ${chatOpen ? "" : "btn-quiet"} justify-start`} aria-pressed={chatOpen}>
          <MessageSquare size={16} aria-hidden /> Assistant
        </button>
      </div>
    </aside>
  );
}
