import { useState, type FormEvent } from "react";
import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { api, type SectionSpec } from "../lib/api";

type Item = Record<string, unknown>;

function toForm(fields: SectionSpec["fields"], item?: Item): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    const v = item?.[f.name];
    out[f.name] = f.kind === "lines" ? (Array.isArray(v) ? v.join("\n") : "") : f.kind === "bool" ? (v ? "true" : "") : v == null ? "" : String(v);
  }
  return out;
}

function fromForm(fields: SectionSpec["fields"], form: Record<string, string>): Item {
  const out: Item = {};
  for (const f of fields) out[f.name] = f.kind === "lines" ? form[f.name].split("\n").map((l) => l.trim()).filter(Boolean) : f.kind === "bool" ? form[f.name] === "true" : form[f.name].trim();
  return out;
}

function ItemForm({ spec, initial, onSubmit, onDelete, submitLabel }: { spec: SectionSpec; initial?: Item; onSubmit: (item: Item) => Promise<void>; onDelete?: () => Promise<void>; submitLabel: string }) {
  const [form, setForm] = useState(() => toForm(spec.fields, initial));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await onSubmit(fromForm(spec.fields, form)); if (!initial) setForm(toForm(spec.fields)); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className={`grid gap-2 border-t border-line px-3 py-3 ${initial ? "" : "bg-bg"}`}>
      {spec.fields.filter((f) => f.kind === "bool").map((f) => (
        <label key={f.name} className="flex items-center gap-2 text-[13px] text-text-2">
          <input type="checkbox" className="h-4 w-4 accent-[var(--color-accent)]" checked={form[f.name] === "true"} onChange={(e) => setForm({ ...form, [f.name]: e.target.checked ? "true" : "" })} />
          {f.name === "hidden" ? "Hide on the CV (stays in your profile)" : f.name}
        </label>
      ))}
      {spec.fields.filter((f) => f.kind !== "bool").map((f) => (
        <label key={f.name} className="grid gap-1">
          <span className="label mb-0 capitalize">{f.name.replace("_", " ")}</span>
          {f.kind === "lines"
            ? <textarea className="input min-h-[64px]" rows={initial ? 3 : 2} value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} placeholder="One per line" />
            : <input className="input" value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} />}
        </label>
      ))}
      {error && <p role="alert" className="text-[12.5px] text-bad">{error}</p>}
      <div className="flex gap-1.5">
        <button className="btn btn-sm" disabled={busy}>{initial ? submitLabel : <><Plus size={14} /> {submitLabel}</>}</button>
        {onDelete && <button type="button" className="btn btn-sm btn-quiet hover:text-bad" onClick={onDelete} disabled={busy}><Trash2 size={14} /> Remove</button>}
      </div>
    </form>
  );
}

export default function SectionEditor({ spec, items, onChange }: { spec: SectionSpec; items: Item[]; onChange: () => void }) {
  const [open, setOpen] = useState(items.length > 0);
  return (
    <section className="mb-2.5 rounded-xl border border-line bg-bg-2">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-3 py-2.5 text-left" aria-expanded={open}>
        <b className="text-[14px]">{spec.title}</b>
        <span className="text-text-3">{items.length}</span>
        <ChevronDown size={16} className={`ml-auto text-text-3 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && (
        <>
          {items.map((item, i) => (
            <ItemForm key={`${i}-${JSON.stringify(item)}`} spec={spec} initial={item} submitLabel="Save"
              onSubmit={async (it) => { await api.putItem(spec.key, i, it); onChange(); }}
              onDelete={async () => { await api.deleteItem(spec.key, i); onChange(); }} />
          ))}
          <ItemForm spec={spec} submitLabel={`Add ${spec.title.toLowerCase()}`} onSubmit={async (it) => { await api.addItem(spec.key, it); onChange(); }} />
        </>
      )}
    </section>
  );
}
