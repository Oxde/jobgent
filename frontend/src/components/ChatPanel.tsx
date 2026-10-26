import { useEffect, useRef, useState, type FormEvent } from "react";
import { Copy, X } from "lucide-react";
import { api, type ChatMessage } from "../lib/api";
import { useLoad, useStore } from "../lib/store";

const MCP_CMD = "claude mcp add jobgent -- uv --directory ~/jobgent run jobgent mcp";

const EXAMPLES = [
  "Rewrite my summary for AI engineering internships",
  "Add SQL to my skills, evidence: database course 2024",
  "Shorten the bullets in my first job",
];

/** The assistant. Used inside the Me page and as the drawer on other pages. */
export default function ChatPanel({ onClose, title = "Assistant" }: { onClose?: () => void; title?: string }) {
  const { bumpProfile } = useStore();
  const { data: settings } = useLoad(() => api.settings(), []);
  const hasKey = settings?.keys.find((k) => k.name === "ANTHROPIC_API_KEY")?.present ?? true;
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api.assistantHistory().then(setHistory).catch(() => undefined); }, []);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [history, busy]);

  async function send(message: string) {
    if (!message.trim() || busy) return;
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
  function submit(e: FormEvent) { e.preventDefault(); void send(text); }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <b className="font-display text-[15px]">{title}</b>
        <div className="flex gap-1">
          {history.length > 0 && <button type="button" className="btn btn-quiet btn-sm" onClick={() => api.assistantClear().then(setHistory)}>Clear</button>}
          {onClose && <button type="button" className="btn btn-quiet btn-sm" onClick={onClose} aria-label="Close assistant"><X size={16} /></button>}
        </div>
      </div>

      <div ref={logRef} className="flex flex-1 flex-col gap-2.5 overflow-y-auto px-4 py-3">
        {!hasKey && (
          <div className="rounded-xl border border-line-2 bg-bg-3 p-3 text-[13px]">
            <b className="block">No API key? Use Claude instead.</b>
            <p className="mt-1 text-text-2">This chat needs an Anthropic key. Without one, connect Jobgent to Claude Code or Claude Desktop and ask it to edit your CV there; this page updates live.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded bg-bg px-2 py-1 text-[12px]">{MCP_CMD}</code>
              <button type="button" className="btn btn-sm" onClick={() => navigator.clipboard.writeText(MCP_CMD).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); })}>
                <Copy size={13} /> {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-2 text-[12px] text-text-3">ChatGPT: run <code>jobgent mcp --http</code> and add it as a connector.</p>
          </div>
        )}
        {history.length === 0 && hasKey && (
          <>
            <p className="text-[13px] text-text-2">Tell me facts about you or ask for changes. Edits go straight into your profile and the CV on the right.</p>
            <div className="flex flex-col gap-1.5">
              {EXAMPLES.map((ex) => <button key={ex} type="button" className="btn btn-sm justify-start text-left font-medium text-text-2" onClick={() => send(ex)}>{ex}</button>)}
            </div>
          </>
        )}
        {history.map((m, i) => (
          <div key={i} className={`max-w-[92%] whitespace-pre-wrap rounded-xl px-3 py-2 text-[13.5px] ${m.role === "user" ? "self-end bg-text text-bg" : "self-start bg-bg-3"}`}>{m.text}</div>
        ))}
        {busy && <div className="self-start rounded-xl bg-bg-3 px-3 py-2 text-[13px] text-text-2">Thinking…</div>}
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-line px-4 py-3">
        <label className="sr-only" htmlFor="chat-input">Message</label>
        <input id="chat-input" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={hasKey ? "Ask for a change…" : "Needs an Anthropic key"} autoComplete="off" disabled={!hasKey} />
        <button className="btn btn-primary" disabled={busy || !text.trim() || !hasKey}>Send</button>
      </form>
    </div>
  );
}
