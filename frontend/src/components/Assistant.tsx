import { useLocation } from "react-router-dom";
import { useStore } from "../lib/store";
import ChatPanel from "./ChatPanel";

/** Right-hand drawer on every page except Me, which has the chat built in. */
export default function Assistant() {
  const { chatOpen, setChatOpen } = useStore();
  const { pathname } = useLocation();
  if (!chatOpen || pathname === "/me") return <aside aria-hidden className="overflow-hidden" />;
  return (
    <aside className="h-full min-w-0 border-l border-line bg-bg-2" aria-label="Assistant">
      <ChatPanel onClose={() => setChatOpen(false)} />
    </aside>
  );
}
