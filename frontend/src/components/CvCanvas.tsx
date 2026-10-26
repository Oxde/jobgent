import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";

const A4_W = 794; // 210mm at 96 dpi
const A4_H = 1123; // 297mm

/**
 * The CV as real A4 pages, scaled to fit the column, editable in place.
 * Reloads whenever the profile changes anywhere (this page, the chat, Claude over MCP).
 */
export default function CvCanvas({ template, editable, src: fixedSrc }: { template: string; editable: boolean; src?: string }) {
  const { bumpProfile } = useStore();
  const wrap = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const [scale, setScale] = useState(1);
  const [height, setHeight] = useState(A4_H);
  const [nonce, setNonce] = useState(0);
  const [toast, setToast] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const known = useRef<string | null>(null);
  const editing = useRef(false);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setScale(Math.min(1.25, (entry.contentRect.width - 48) / A4_W)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  // Live refresh: poll the profile version; skip while the user is typing in the page.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const { version } = await api.profileVersion();
        if (!alive) return;
        if (known.current !== null && version !== known.current && !editing.current) { reload(); bumpProfile(); }
        known.current = version;
      } catch { /* server restarting; try again */ }
    };
    void tick();
    const id = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(id); };
  }, [reload, bumpProfile]);

  useEffect(() => { reload(); }, [template, reload]);

  // Messages from the editable page.
  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const d = e.data as { source?: string; type?: string; path?: string; detail?: string };
      if (d?.source !== "jobgent-cv") return;
      if (d.type === "saved") {
        api.profileVersion().then(({ version }) => { known.current = version; });
        bumpProfile();
        setToast({ kind: "ok", text: "Saved to your profile" });
      } else if (d.type === "error") {
        setToast({ kind: "error", text: `Not saved (${d.path}): ${d.detail}` });
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [bumpProfile]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), toast.kind === "ok" ? 1400 : 5000);
    return () => clearTimeout(id);
  }, [toast]);

  function onLoad() {
    const doc = frame.current?.contentDocument;
    if (!doc) return;
    setHeight(Math.max(A4_H, doc.documentElement.scrollHeight));
    doc.addEventListener("focusin", () => { editing.current = true; });
    doc.addEventListener("focusout", () => { editing.current = false; });
  }

  const pages = Math.ceil(height / A4_H);
  const src = fixedSrc ? `${fixedSrc}${fixedSrc.includes("?") ? "&" : "?"}n=${nonce}` : `/api/cv/preview?template=${encodeURIComponent(template)}${editable ? "&edit=1" : ""}&n=${nonce}`;

  return (
    <div ref={wrap} className="relative min-h-0 overflow-auto rounded-xl bg-[#2a2f3a] p-6">
      <div style={{ width: A4_W * scale, height: height * scale }} className="mx-auto">
        <iframe
          ref={frame}
          key={nonce}
          title="Your CV"
          src={src}
          onLoad={onLoad}
          scrolling="no"
          style={{ width: A4_W, height, transform: `scale(${scale})`, transformOrigin: "top left" }}
          className="block border-0 bg-white shadow-[0_8px_40px_rgba(0,0,0,.45)]"
        />
      </div>
      {pages > 1 && <p className="mt-3 text-center text-[12.5px] text-warn">This CV runs to {pages} pages. Aim for one: ask the chat to shorten it.</p>}
      {toast && (
        <div role="status" className={`fixed bottom-5 right-5 z-20 rounded-lg px-3 py-2 text-[13px] shadow-lg ${toast.kind === "ok" ? "bg-ok text-bg" : "bg-bad text-bg"}`}>{toast.text}</div>
      )}
    </div>
  );
}
