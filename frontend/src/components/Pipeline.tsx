import { createContext, useContext, useRef, useState } from "react";
import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { Link } from "react-router-dom";
import { api, type Card, type Column, type Status } from "../lib/api";
import { useLoad, useStore } from "../lib/store";
import { Empty, ErrorNote, JobLink, STATUS_LABEL } from "./ui";

/** When the last drag ended; a click right after a drop must not open the card. */
const LastDrag = createContext<{ current: number }>({ current: 0 });

/** Columns a card can be dropped into. "no_answer" is computed from the applied date, not a status. */
const DROPPABLE: Record<string, Status | undefined> = { liked: "liked", pack_ready: "pack_ready", applied: "applied", interview: "interview", offer: "offer", rejected: "rejected" };

export default function Pipeline() {
  const { refreshStats } = useStore();
  const { data, error, reload } = useLoad(() => api.applications(), []);
  const [list, setList] = useState(false);
  const [moving, setMoving] = useState<number | null>(null);
  const lastDrag = useRef(0);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  async function move(jobId: number, status: Status) {
    setMoving(jobId);
    try {
      await api.setStatus(jobId, status);
      refreshStats();
      reload();
    } finally {
      setMoving(null);
    }
  }

  function onDragEnd(e: DragEndEvent) {
    lastDrag.current = Date.now();
    const target = e.over?.id ? DROPPABLE[String(e.over.id)] : undefined;
    const jobId = Number(e.active.id);
    if (!target || !jobId) return;
    const from = data?.find((c) => c.cards.some((card) => card.job.id === jobId));
    if (from && DROPPABLE[from.key] === target) return;
    void move(jobId, target);
  }

  if (error) return <ErrorNote message={error} />;
  if (!data) return <p className="text-text-2">Loading…</p>;
  const total = data.reduce((n, c) => n + c.cards.length, 0);
  if (total === 0) return <Empty>Nothing in the pipeline yet. Save a job from Find and it lands here.</Empty>;

  return (
    <>
      <div className="mb-3 flex justify-end">
        <button className="btn btn-quiet btn-sm" onClick={() => setList((v) => !v)} aria-pressed={list}>{list ? "Show board" : "Show list"}</button>
      </div>
      {list ? (
        <table className="w-full border-collapse">
          <thead><tr className="text-left text-[12px] text-text-3"><th className="pb-2 pl-2 font-medium">Role</th><th className="pb-2 font-medium">Company</th><th className="pb-2 font-medium">Stage</th><th className="pb-2 font-medium">Since</th><th className="pb-2 font-medium">CV</th></tr></thead>
          <tbody>
            {data.flatMap((col) => col.cards.map((card) => (
              <tr key={card.job.id} className="border-t border-line">
                <td className="py-2 pl-2 pr-3"><JobLink id={card.job.id} className="font-semibold">{card.job.title}</JobLink></td>
                <td className="py-2 pr-3">{card.job.company}</td>
                <td className="py-2 pr-3">
                  <select className="input w-auto py-1" value={card.job.status} onChange={(e) => move(card.job.id, e.target.value as Status)} aria-label={`Stage for ${card.job.title}`}>
                    {Object.entries(DROPPABLE).map(([k, s]) => s && <option key={k} value={s}>{STATUS_LABEL[s]}</option>)}
                  </select>
                </td>
                <td className="py-2 pr-3 text-text-2">{card.days_since !== null ? `${card.days_since} d` : ""}</td>
                <td className="py-2 pr-3">{card.has_pack && <a className="btn btn-sm" href={`/packs/${card.job.id}/cv.pdf`} target="_blank" rel="noopener">PDF</a>}</td>
              </tr>
            )))}
          </tbody>
        </table>
      ) : (
        <LastDrag.Provider value={lastDrag}>
          <DndContext sensors={sensors} onDragEnd={onDragEnd}>
            <div className="grid gap-3 overflow-x-auto pb-2 select-none" style={{ gridTemplateColumns: `repeat(${data.length}, minmax(140px, 1fr))` }}>
              {data.map((col) => <ColumnView key={col.key} col={col} moving={moving} />)}
            </div>
          </DndContext>
        </LastDrag.Provider>
      )}
    </>
  );
}

function ColumnView({ col, moving }: { col: Column; moving: number | null }) {
  const droppable = Boolean(DROPPABLE[col.key]);
  const { setNodeRef, isOver } = useDroppable({ id: col.key, disabled: !droppable });
  return (
    <div ref={setNodeRef} className={`min-h-[160px] rounded-xl border p-2 transition-colors ${isOver && droppable ? "border-accent bg-accent/5" : "border-line bg-bg-2/60"}`}>
      <h2 className="mb-2 flex items-center justify-between px-1 text-[13px] font-bold text-text-2">{col.title}<span className="font-medium text-text-3">{col.cards.length}</span></h2>
      {col.cards.map((card) => <CardView key={card.job.id} card={card} dimmed={moving === card.job.id} />)}
    </div>
  );
}

function CardView({ card, dimmed }: { card: Card; dimmed: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: card.job.id });
  const lastDrag = useContext(LastDrag);
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  return (
    <div ref={setNodeRef} style={style} {...listeners} {...attributes} className={`mb-2 cursor-grab rounded-lg border border-line bg-bg-2 p-2.5 touch-none ${isDragging ? "z-10 opacity-90 shadow-xl" : ""} ${dimmed ? "opacity-50" : ""}`}>
      <Link to={`/jobs/${card.job.id}`} className="block text-[13.5px] font-semibold leading-tight hover:underline" onClick={(e) => { if (Date.now() - lastDrag.current < 400) e.preventDefault(); }}>{card.job.title}</Link>
      <div className="text-[12px] text-text-2">{card.job.company}</div>
      <div className="mt-2 flex items-center gap-2 text-[11.5px] text-text-3">
        {card.days_since !== null && <span>{card.days_since} d ago</span>}
        {card.has_pack && <a className="underline" href={`/packs/${card.job.id}/cv.pdf`} target="_blank" rel="noopener" onPointerDown={(e) => e.stopPropagation()}>CV</a>}
      </div>
      {card.notes && <p className="mt-1.5 text-[12px] text-text-2">{card.notes}</p>}
    </div>
  );
}
