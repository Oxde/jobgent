import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type WeeklyStats } from "./api";

interface Store {
  stats: WeeklyStats | null;
  refreshStats: () => void;
  /** Bumped whenever the profile changes anywhere (editor, assistant); pages re-fetch on it. */
  profileVersion: number;
  bumpProfile: () => void;
  chatOpen: boolean;
  setChatOpen: (open: boolean) => void;
}

const Ctx = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [stats, setStats] = useState<WeeklyStats | null>(null);
  const [profileVersion, setProfileVersion] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const refreshStats = useCallback(() => { api.stats().then(setStats).catch(() => setStats(null)); }, []);
  const bumpProfile = useCallback(() => setProfileVersion((v) => v + 1), []);
  useEffect(() => { refreshStats(); }, [refreshStats, profileVersion]);
  const value = useMemo(() => ({ stats, refreshStats, profileVersion, bumpProfile, chatOpen, setChatOpen }), [stats, refreshStats, profileVersion, bumpProfile, chatOpen]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside StoreProvider");
  return s;
}

/** Load something async; `deps` re-run it. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn().then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}
