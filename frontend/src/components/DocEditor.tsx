import { useEffect, useState } from "react";
import { EyeOff, History, Pencil, RotateCcw, Sparkles, Undo2 } from "lucide-react";
import { api, type DocKind, type DocumentView, type Unit } from "../lib/api";
import { useToast } from "./Toast";

/** Edit a pack document piece by piece: by hand, with the AI, leave out / put back, undo and history. */
export default function DocEditor({ jobId, kind, doc, onChange }: { jobId: number; kind: DocKind; doc: DocumentView; onChange: () => void }) {
  const toast = useToast();
  const [showHistory, setShowHistory] = useState(false);
  const aiChanges = doc.versions.length - 1;

  async function run(action: () => Promise<unknown>, done?: string) {
    try { await action(); if (done) toast.show(done, { tone: "ok" }); onChange(); } catch (e) { toast.show((e as Error).message, { tone: "error" }); }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn btn-sm" disabled={aiChanges < 1} onClick={() => run(() => api.undoDoc(jobId, kind), "Undone")}><Undo2 size={14} /> Undo last AI change</button>
        <button className="btn btn-quiet btn-sm" onClick={() => setShowHistory((v) => !v)} aria-expanded={showHistory}><History size={14} /> History ({doc.versions.length})</button>
      </div>
      {showHistory && (
        <ul className="rounded-lg border border-line bg-bg-2 p-2 text-[12.5px]">
          {[...doc.versions].reverse().map((v) => (
            <li key={v.id} className="flex items-center gap-2 py-1">
              <span className="w-32 shrink-0 text-text-3">{new Date(v.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
              <span className="min-w-0 flex-1 truncate">{v.cause}{v.detail ? `: ${v.detail}` : ""}</span>
              <button className="btn btn-quiet btn-sm" onClick={() => run(() => api.restoreDoc(jobId, kind, v.id), "Restored")}><RotateCcw size={13} /> Restore</button>
            </li>
          ))}
        </ul>
      )}
      {doc.trimmed.length > 0 && (
        <div className="rounded-lg border border-line bg-bg-2 p-2 text-[12.5px]">
          <div className="mb-1 text-text-3">Left out</div>
          {doc.trimmed.map((t, i) => (
            <div key={i} className="flex items-center gap-2 py-0.5">
              <span className="min-w-0 flex-1 truncate">{t.label}</span>
              <button className="btn btn-quiet btn-sm" onClick={() => run(() => api.putBack(jobId, kind, i), "Put back")}>Put back</button>
            </div>
          ))}
        </div>
      )}
      <ul className="flex flex-col gap-1.5">
        {doc.units.map((u) => <UnitRow key={u.id} jobId={jobId} kind={kind} unit={u} onChange={onChange} />)}
      </ul>
    </div>
  );
}

function UnitRow({ jobId, kind, unit, onChange }: { jobId: number; kind: DocKind; unit: Unit; onChange: () => void }) {
  const toast = useToast();
  const [mode, setMode] = useState<"view" | "edit" | "ai">("view");
  const [text, setText] = useState(unit.text);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setText(unit.text), [unit.text]);
  const canLeaveOut = kind === "cv" && /^(experience\[\d+\]\.bullets\[\d+\]|projects\[\d+\]\.description)$/.test(unit.id);

  async function saveEdit() {
    setBusy(true);
    try { await api.editUnit(jobId, kind, unit.id, text); setMode("view"); onChange(); } catch (e) { toast.show((e as Error).message, { tone: "error" }); } finally { setBusy(false); }
  }
  async function askAi() {
    if (!instruction.trim()) return;
    setBusy(true);
    try {
      const r = await api.aiUnit(jobId, kind, unit.id, instruction);
      if (r.declined) toast.show(r.reason, { tone: "info" });
      else {
        toast.show(r.check_this.length ? `Updated. Check: ${r.check_this.join(", ")}` : "Updated", { tone: "ok", undo: async () => { await api.undoDoc(jobId, kind); onChange(); } });
        setMode("view"); setInstruction("");
      }
      onChange();
    } catch (e) { toast.show((e as Error).message, { tone: "error" }); } finally { setBusy(false); }
  }

  return (
    <li className="group rounded-lg border border-line bg-bg-2 px-3 py-2">
      <div className="mb-0.5 flex items-center gap-2">
        <span className="text-[11.5px] text-text-3">{unit.label}</span>
        <div className="ml-auto flex gap-1 opacity-60 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <button className="btn btn-quiet btn-sm" onClick={() => setMode(mode === "edit" ? "view" : "edit")} aria-label={`Edit ${unit.label}`}><Pencil size={13} /> Edit</button>
          <button className="btn btn-quiet btn-sm" onClick={() => setMode(mode === "ai" ? "view" : "ai")} aria-label={`Ask AI about ${unit.label}`}><Sparkles size={13} /> Ask AI</button>
          {canLeaveOut && <button className="btn btn-quiet btn-sm" onClick={() => api.leaveOut(jobId, kind, unit.id).then(onChange).catch((e: Error) => toast.show(e.message, { tone: "error" }))} aria-label={`Leave out ${unit.label}`}><EyeOff size={13} /> Leave out</button>}
        </div>
      </div>
      {mode === "edit" ? (
        <div className="flex flex-col gap-1.5">
          <textarea className="input min-h-[60px]" value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(8, Math.max(2, Math.ceil(text.length / 80)))} />
          <div className="flex gap-1.5"><button className="btn btn-sm btn-primary" disabled={busy} onClick={saveEdit}>Save</button><button className="btn btn-quiet btn-sm" onClick={() => { setText(unit.text); setMode("view"); }}>Cancel</button></div>
        </div>
      ) : (
        <p className="whitespace-pre-wrap text-[13.5px]">{unit.text || <span className="text-text-3">empty</span>}</p>
      )}
      {mode === "ai" && (
        <form className="mt-1.5 flex gap-1.5" onSubmit={(e) => { e.preventDefault(); void askAi(); }}>
          <input className="input" autoFocus placeholder="e.g. lead with Python, shorter, mention their GenAI team" value={instruction} onChange={(e) => setInstruction(e.target.value)} />
          <button className="btn btn-sm btn-primary" disabled={busy || !instruction.trim()}>{busy ? "…" : "Rewrite"}</button>
        </form>
      )}
    </li>
  );
}
