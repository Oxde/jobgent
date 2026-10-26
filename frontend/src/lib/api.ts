export type Status = "new" | "liked" | "pack_ready" | "applied" | "interview" | "offer" | "rejected" | "skipped";
export const STATUSES: Status[] = ["new", "liked", "pack_ready", "applied", "interview", "offer", "rejected", "skipped"];

export interface JobSummary { id: number; title: string; company: string; location: string | null; score: number | null; status: Status; url: string; posted_at: string | null; source: string; verdict: Verdict | null; deadline: string | null; age_days: number | null; also_in: number; }
export type Verdict = "apply" | "consider" | "skip";
export interface JobDetail extends JobSummary { description: string; reasons: string[]; gaps: string[]; start_hint: string | null; months: number | null; dutch_plus: boolean | null; pack_dir: string | null; }
export interface Dim { name: string; value: number; max: number; }
export interface AtsReport { percent: number; matched: string[]; missing: string[]; }
export interface PackResult { job_id: number; dir: string; cv_pdf: string; letter_md: string; change_summary: string[]; apply_url: string; apply_email: string | null; created_at: string; review_applied: string[]; review_notes: Record<string, string>; check_this: string[]; tone: string; ats_ok: boolean; ats_problems: string[]; keywords: Record<string, string[]>; }
export interface Gate { name: string; status: "pass" | "flag" | "fail"; reason: string; }
export interface RequirementRow { text: string; kind: string; importance: "critical" | "high" | "nice"; basis: string; status: "covered" | "partial" | "gap"; evidence: string; }
export interface EvaluationView { verdict: Verdict; verdict_reason: string; summary: string; deadline: string | null; coverage: number; gates: Gate[]; requirements: RequirementRow[]; created_at: string; }
export interface Unit { id: string; label: string; text: string; }
export interface VersionView { id: number; cause: string; detail: string; created_at: string; }
export interface DocumentView { units: Unit[]; trimmed: { label: string }[]; versions: VersionView[]; }
export type DocKind = "cv" | "letter" | "email" | "followup";
export interface TimelineItem { kind: string; text: string; at: string; }
export interface AiEditResult { declined: boolean; reason: string; check_this: string[]; }
export interface Funnel { sent: number; heard_back: number; interview: number; offer: number; response_rate: number; }
export interface JobPage { job: JobDetail; dims: Dim[] | null; ats: AtsReport | null; pack: PackResult | null; letter: string | null; evaluation: EvaluationView | null; }
export interface WeeklyStats { applied_this_week: number; goal: number; by_status: Record<string, number>; }
export interface ChecklistItem { label: string; done: boolean; hint: string; }
export interface ActionItem { kind: "offer" | "interview_soon" | "send" | "make_pack" | "follow_up"; job: JobSummary; days_since: number | null; text: string; }
export interface HomeData { top_matches: JobSummary[]; actions: ActionItem[]; stats: WeeklyStats; checklist: ChecklistItem[]; weeks_left: number; start_from: string; funnel: Funnel | null; weekly: { week_start: string; sent: number }[]; }
export interface Card { job: JobSummary; days_since: number | null; applied_at: string | null; notes: string; has_pack: boolean; }
export interface Column { key: string; title: string; cards: Card[]; }
export interface Personal { name: string; headline: string; location: string; email: string; phone: string; linkedin: string; github: string; }
export interface Profile { verified: boolean; personal: Personal; summary: string; education: Record<string, unknown>[]; experience: Record<string, unknown>[]; projects: Record<string, unknown>[]; skills: Record<string, unknown>[]; languages: Record<string, unknown>[]; preferences: { weekly_goal: number; template: string; remote_ok: boolean }; search: { keywords: string[]; locations: string[]; start_from: string; start_to: string; months_min: number; months_max: number }; }
export interface FieldSpec { name: string; kind: "text" | "lines" | "bool"; }
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
  evaluate: (id: number) => request<EvaluationView>(`/jobs/${id}/evaluate`, { method: "POST" }),
  documents: (id: number) => request<Record<DocKind, DocumentView | null>>(`/jobs/${id}/documents`),
  editUnit: (id: number, kind: DocKind, unit: string, text: string) => request<DocumentView>(`/jobs/${id}/documents/${kind}?unit=${encodeURIComponent(unit)}`, { method: "PATCH", body: JSON.stringify({ text }) }),
  aiUnit: (id: number, kind: DocKind, unit: string, instruction: string) => request<AiEditResult>(`/jobs/${id}/documents/${kind}/ai?unit=${encodeURIComponent(unit)}`, json({ instruction })),
  leaveOut: (id: number, kind: DocKind, unit: string) => request<DocumentView>(`/jobs/${id}/documents/${kind}/leave-out?unit=${encodeURIComponent(unit)}`, { method: "POST" }),
  putBack: (id: number, kind: DocKind, index: number) => request<DocumentView>(`/jobs/${id}/documents/${kind}/put-back/${index}`, { method: "POST" }),
  undoDoc: (id: number, kind: DocKind) => request<DocumentView>(`/jobs/${id}/documents/${kind}/undo`, { method: "POST" }),
  restoreDoc: (id: number, kind: DocKind, versionId: number) => request<DocumentView>(`/jobs/${id}/documents/${kind}/restore/${versionId}`, { method: "POST" }),
  undoStatus: (id: number) => request<JobSummary>(`/jobs/${id}/status/undo`, { method: "POST" }),
  setInterview: (id: number, at: string) => request<JobSummary>(`/jobs/${id}/interview`, json({ at })),
  addNote: (id: number, text: string) => request<TimelineItem[]>(`/jobs/${id}/notes`, json({ text })),
  timeline: (id: number) => request<TimelineItem[]>(`/jobs/${id}/timeline`),
  followup: (id: number) => request<{ subject: string; body: string }>(`/jobs/${id}/followup`, { method: "POST" }),
  followupSent: (id: number) => request<TimelineItem[]>(`/jobs/${id}/followup/sent`, { method: "POST" }),
};
