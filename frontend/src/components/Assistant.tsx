import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { api, type ChatMessage } from "../lib/api";
import { useStore } from "../lib/store";

export default function Assistant() {
  const { chatOpen, setChatOpen, bumpProfile } = useStore();
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (chatOpen) api.assistantHistory().then(setHistory).catch(() => undefined); }, [chatOpen]);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [history, busy]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setHistory((h) => [...h, { role: "user", text: message }]);
    setBusy(true);
    try {
      const res = await api.assistantSend(message);
      setHistory(res.history);
      if (res.applied.length) bumpProfile();
    } catch (err) {
      setHistory((h) => [...h, { role: "assistant", text: `Request failed: ${(err as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  if (!chatOpen) return <aside aria-hidden className="overflow-hidden" />;
  return (
    <aside className="flex h-full min-w-0 flex-col border-l border-line bg-bg-2" aria-label="Assistant">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <b className="font-display text-[15px]">Assistant</b>
        <div className="flex gap-1">
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => api.assistantClear().then(setHistory)}>Clear</button>
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => setChatOpen(false)} aria-label="Close assistant"><X size={16} /></button>
        </div>
      </div>
      <div ref={logRef} className="flex flex-1 flex-col gap-2.5 overflow-y-auto px-4 py-3">
        {history.length === 0 && (
          <p className="text-[13px] text-text-2">
            I know your profile. Tell me things ("I did a hackathon in 2025, built a Flask app") or ask for changes ("set my weekly goal to 12", "add SQL to my skills, evidence: database course"). What I change is written to your profile and listed here.
          </p>
        )}
        {history.map((m, i) => (
          <div key={i} className={`max-w-[92%] whitespace-pre-wrap rounded-xl px-3 py-2 text-[13.5px] ${m.role === "user" ? "self-end bg-text text-bg" : "self-start bg-bg-3"}`}>{m.text}</div>
        ))}
        {busy && <div className="self-start rounded-xl bg-bg-3 px-3 py-2 text-[13px] text-text-2">Thinking…</div>}
      </div>
      <form onSubmit={send} className="flex gap-2 border-t border-line px-4 py-3">
        <label className="sr-only" htmlFor="assistant-input">Message</label>
        <input id="assistant-input" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Tell me a fact, or ask for a change…" autoComplete="off" />
        <button className="btn btn-primary" disabled={busy || !text.trim()}>Send</button>
      </form>
    </aside>
  );
}
