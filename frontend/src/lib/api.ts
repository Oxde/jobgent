export type Status = "new" | "liked" | "pack_ready" | "applied" | "interview" | "offer" | "rejected" | "skipped";
export const STATUSES: Status[] = ["new", "liked", "pack_ready", "applied", "interview", "offer", "rejected", "skipped"];

export interface JobSummary { id: number; title: string; company: string; location: string | null; score: number | null; status: Status; url: string; posted_at: string | null; source: string; }
export interface JobDetail extends JobSummary { description: string; reasons: string[]; gaps: string[]; start_hint: string | null; months: number | null; dutch_plus: boolean | null; pack_dir: string | null; }
export interface Dim { name: string; value: number; max: number; }
export interface AtsReport { percent: number; matched: string[]; missing: string[]; }
export interface PackResult { job_id: number; dir: string; cv_pdf: string; letter_md: string; change_summary: string[]; apply_url: string; apply_email: string | null; created_at: string; }
export interface JobPage { job: JobDetail; dims: Dim[] | null; ats: AtsReport | null; pack: PackResult | null; letter: string | null; }
export interface WeeklyStats { applied_this_week: number; goal: number; by_status: Record<string, number>; }
export interface ChecklistItem { label: string; done: boolean; hint: string; }
export interface ActionItem { kind: "make_pack" | "send" | "follow_up"; job: JobSummary; days_since: number | null; text: string; }
export interface HomeData { top_matches: JobSummary[]; actions: ActionItem[]; stats: WeeklyStats; checklist: ChecklistItem[]; weeks_left: number; start_from: string; }
export interface Card { job: JobSummary; days_since: number | null; applied_at: string | null; notes: string; has_pack: boolean; }
export interface Column { key: string; title: string; cards: Card[]; }
export interface Personal { name: string; headline: string; location: string; email: string; phone: string; linkedin: string; github: string; }
export interface Profile { verified: boolean; personal: Personal; summary: string; education: Record<string, unknown>[]; experience: Record<string, unknown>[]; projects: Record<string, unknown>[]; skills: Record<string, unknown>[]; languages: Record<string, unknown>[]; preferences: { weekly_goal: number; template: string; remote_ok: boolean }; search: { keywords: string[]; locations: string[]; start_from: string; start_to: string; months_min: number; months_max: number }; }
export interface FieldSpec { name: string; kind: "text" | "lines"; }
export interface SectionSpec { key: "education" | "experience" | "projects" | "skills" | "languages"; title: string; fields: FieldSpec[]; }
export interface TemplateInfo { id: string; name: string; description: string; color: string; }
export interface ProfilePage { profile: Profile; checklist: ChecklistItem[]; voice: string; templates: TemplateInfo[]; sections: SectionSpec[]; master_cv: boolean; }
export interface ChatMessage { role: "user" | "assistant"; text: string; }
export interface ChatResponse { reply: string; applied: string[]; failed: string[]; history: ChatMessage[]; }
export interface SettingsPage { keys: { name: string; present: boolean; hint: string }[]; home_dir: string; companies: number; fast_model: string; smart_model: string; }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* no body */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  home: () => request<HomeData>("/home"),
  stats: () => request<WeeklyStats>("/stats"),
  jobs: (p: { q?: string; min_score?: number; status?: string } = {}) => {
    const qs = new URLSearchParams();
    if (p.q) qs.set("q", p.q);
    if (p.min_score) qs.set("min_score", String(p.min_score));
    if (p.status) qs.set("status", p.status);
    const s = qs.toString();
    return request<JobSummary[]>(`/jobs${s ? `?${s}` : ""}`);
  },
  job: (id: number) => request<JobPage>(`/jobs/${id}`),
  setStatus: (id: number, status: Status, notes?: string) => request<JobSummary>(`/jobs/${id}/status`, json({ status, notes })),
  makePack: (id: number) => request<PackResult>(`/jobs/${id}/pack`, { method: "POST" }),
  applications: () => request<Column[]>("/applications"),
  profile: () => request<ProfilePage>("/profile"),
  patchProfile: (path: string, value: string) => request<Profile>("/profile", { method: "PATCH", body: JSON.stringify({ path, value }) }),
  addItem: (section: string, item: Record<string, unknown>) => request<Profile>(`/profile/${section}`, json(item)),
  putItem: (section: string, index: number, item: Record<string, unknown>) => request<Profile>(`/profile/${section}/${index}`, { method: "PUT", body: JSON.stringify(item) }),
  deleteItem: (section: string, index: number) => request<Profile>(`/profile/${section}/${index}`, { method: "DELETE" }),
  setVoice: (text: string) => request<{ voice: string }>("/profile/voice", json({ text })),
  importProfile: (json_path: string) => request<Profile>("/profile/import", json({ json_path })),
  templates: () => request<TemplateInfo[]>("/templates"),
  assistantHistory: () => request<ChatMessage[]>("/assistant"),
  assistantSend: (message: string) => request<ChatResponse>("/assistant", json({ message })),
  assistantClear: () => request<ChatMessage[]>("/assistant", { method: "DELETE" }),
  settings: () => request<SettingsPage>("/settings"),
  profileVersion: () => request<{ version: string }>("/profile/version"),
};
