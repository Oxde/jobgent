import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

interface ToastItem { id: number; text: string; undo?: () => void | Promise<void>; tone: "ok" | "error" | "info"; }
interface ToastApi { show: (text: string, opts?: { undo?: () => void | Promise<void>; tone?: ToastItem["tone"] }) => void; }

const Ctx = createContext<ToastApi>({ show: () => undefined });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const show = useCallback<ToastApi["show"]>((text, opts) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-2), { id, text, undo: opts?.undo, tone: opts?.tone ?? "info" }]);
  }, []);
  return (
    <Ctx.Provider value={{ show }}>
      {children}
      <div className="pointer-events-none fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2" aria-live="polite">
        {items.map((t) => <Toast key={t.id} item={t} onDone={() => setItems((xs) => xs.filter((x) => x.id !== t.id))} />)}
      </div>
    </Ctx.Provider>
  );
}

function Toast({ item, onDone }: { item: ToastItem; onDone: () => void }) {
  useEffect(() => { const id = setTimeout(onDone, item.undo ? 6000 : 3000); return () => clearTimeout(id); }, [item, onDone]);
  const tone = item.tone === "error" ? "bg-bad text-bg" : item.tone === "ok" ? "bg-ok text-bg" : "bg-text text-bg";
  return (
    <div className={`pointer-events-auto flex items-center gap-3 rounded-lg px-4 py-2.5 text-[13.5px] shadow-xl ${tone}`} role="status">
      <span>{item.text}</span>
      {item.undo && <button className="font-semibold underline" onClick={async () => { await item.undo?.(); onDone(); }}>Undo</button>}
    </div>
  );
}

export const useToast = () => useContext(Ctx);
