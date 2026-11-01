import { DEFAULT_API_BASE_URL, type UploadCheck, type CustomerMeeting, type GovSource, type ReportItem, type ReportSection, type DocumentRequest } from "@homexo/shared";

// Staff workspace API (backend/app/admin.py). Kept out of @homexo/shared because only the website uses it.
const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;
const TOKEN_KEY = "homexo.staff.token";

export type StaffUser = {
  id: string; name: string; email: string | null; phone: string | null; role: "admin" | "agent"; account_status?: string;
  // Whether the team can call them now. The phone number is for the team only; customers never see it.
  available_for_calls: boolean; availability_note: string | null; availability_updated_at: string | null;
};
export type TeamMember = StaffUser & { lawyer: boolean };
export type StaffRef = { id: string; name: string } | null;

// Mirrors meeting_view(staff=True) in backend/app/tickets.py.
export type Meeting = CustomerMeeting & {
  lawyer: { id: string; name: string };
  ticket_number: string;
  service_name: string;
  customer_name: string;
  customer_phone: string | null;
  calendar: "google" | "manual";
};

// Mirrors document_view(staff=True) and staff_report_view in backend/app/case_files.py.
export type StaffDocument = {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  tag: string | null;
  note: string | null;
  at: string;
  download_url: string;
  uploaded_by: "customer" | "staff" | "system";
  checksum_sha256: string | null;
  check?: UploadCheck | null;
};
export type StaffReport = {
  status: "draft" | "issued" | "final_generated" | "signed";
  status_label: string;
  issued_at: string | null;
  lawyer: StaffRef;
  reviewer: StaffRef;
  sections: ReportSection[];
  final_sections: ReportSection[];
  items: (ReportItem & { reviewed_at: string | null })[];
  progress: { done: number; total: number };
  checklist_complete: boolean;
  preliminary_pdf_url: string;
  final_pdf_url: string | null;
  final_generated_at: string | null;
  signed_report_url: string | null;
  signed_at: string | null;
};
export type TemplateItem = { tag: string; label: string; guidance: string; fetch_by: "customer" | "homexo"; source: string | null };
export type ReportTemplate = { preliminary: ReportSection[]; final: ReportSection[]; items: TemplateItem[]; sources: GovSource[] };
export type PropertyDetails = {
  type: string; location: string | null; address_line: string | null; survey_number: string | null; subdivision_or_surnoc: string | null;
  property_id_or_pid: string | null; village: string | null; hobli: string | null; taluk: string | null; district: string | null;
};
export type FetchTask = {
  ticket_number: string;
  customer_name: string;
  item: { id: string; tag: string; label: string; guidance: string; status: string; note: string | null };
  source: GovSource | null;
  property: PropertyDetails | null;
};

export type TicketSummary = {
  ticket_number: string;
  title: string;
  customer_name: string;
  phone: string | null;
  service_slug: string;
  service_name: string;
  package: string | null;
  location: string | null;
  status: string;
  status_label: string;
  priority: "low" | "normal" | "high" | "urgent";
  source: string;
  assignee: StaffRef;
  needs_reply: boolean;
  created_at: string;
  updated_at: string;
};

// Mirrors staff_case_view and task_view in backend/app/case_management.py.
export type CaseTask = {
  id: string; title: string; notes: string | null; status: "open" | "done" | "cancelled"; source: "manual" | "playbook"; playbook_key: string | null;
  assignee: StaffRef; due_at: string | null; overdue: boolean; created_at: string; completed_at: string | null;
  case?: { ticket_number: string; service_name: string; customer_name: string; status: string; priority: string };
};
export type CaseDeadlines = { due_at: string | null; overdue: boolean; first_response_due_at: string | null; first_response_at: string | null; first_response_missed: boolean };
export type CaseFee = { status: "none" | "quoted" | "paid" | "waived"; status_label: string; quote: number | null; paid: number | null; paid_at: string | null; reference: string | null; note: string | null };
export type CaseView = {
  milestones: { key: string; label: string; done: boolean; current: boolean }[];
  current_milestone: string;
  deadlines: CaseDeadlines;
  owner: StaffRef;
  team: { user: { id: string; name: string }; role: "associate" | "paralegal" | "reviewer"; role_label: string; added_at: string }[];
  tasks: CaseTask[];
  open_tasks: number;
  overdue_tasks: number;
  fee: CaseFee;
  closure: { can_close: boolean; blockers: string[]; warnings: string[] } | null;
  closed: { outcome: string | null; outcome_label: string | null; summary: string | null; at: string | null } | null;
  allowed_statuses: string[];
  outcomes: { value: string; label: string }[];
};
export type BoardCard = TicketSummary & { milestone: string; deadlines: CaseDeadlines; open_tasks: number; overdue_tasks: number; fee_status: CaseFee["status"]; team: string[] };
export type Board = {
  columns: { key: string; label: string; cards: BoardCard[] }[];
  counts: { open: number; overdue: number; due_this_week: number; first_response_missed: number; overdue_tasks: number; closed_30_days: number };
};

export type TicketDetail = TicketSummary & {
  case: CaseView;
  document_request?: DocumentRequest;
  verification_workflow?: { run_id: string; approval: { name: string; at: string; notes: string; sources: string[] } | null } | null;
  description: string;
  customer: { id: string; name: string; phone: string | null; email: string | null };
  property: PropertyDetails | null;
  events: { type: string; old: Record<string, string> | null; new: Record<string, string> | null; note: string | null; actor: StaffRef; at: string }[];
  messages: { id: string; author_type: "customer" | "staff" | "system"; author: StaffRef; visibility: "customer" | "internal"; message: string; at: string }[];
  meetings: Meeting[];
  documents: StaffDocument[];
  report: StaffReport | null;
  notifications: { channel: string; template: string; recipient: string | null; to: "customer" | "staff"; status: string; error: string | null; at: string; send_after: string | null }[];
  // The website or app chat this ticket was raised from or checked in, oldest first.
  chat_transcript: { from: "customer" | "assistant" | "system" | "agent"; message: string; at: string }[];
};

export type UrgentTicket = TicketSummary & { urgent_note: string | null; flagged_by: string | null; flagged_at: string };

export type Summary = { open: number; new_today: number; unassigned: number; needs_reply: number; urgent: number; by_status: { status: string; label: string; count: number }[] };
export type Meta = {
  statuses: { value: string; label: string }[];
  priorities: string[];
  meetings: { google_calendar: boolean; whatsapp: boolean; timezone: string; reminder_minutes: number[] };
};

export class UnauthorizedError extends Error {}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage blocked: the session lasts until the page is reloaded.
  }
}

export async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${BASE_URL}/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) throw new UnauthorizedError(typeof data.detail === "string" ? data.detail : "Sign in to continue.");
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail
      : Array.isArray(data.detail) && data.detail[0]?.msg ? `${data.detail[0].loc?.at(-1) ?? "Field"}: ${data.detail[0].msg}`
      : "Request failed.";
    throw new Error(detail);
  }
  return data as T;
}

// File uploads: multipart, so the browser sets the Content-Type with its boundary.
export async function adminUpload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const response = await fetch(`${BASE_URL}/api/v1${path}`, { method: "POST", body: form, headers: token ? { Authorization: `Bearer ${token}` } : {} });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) throw new UnauthorizedError("Sign in to continue.");
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Upload failed.");
  return data as T;
}

// Download links in ticket views are short-lived paths on the API.
export const fileHref = (path: string) => `${BASE_URL}${path}`;

const dateTime = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export const formatDate = (iso: string) => dateTime.format(new Date(iso));
const clock = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit" });
export const formatTime = (iso: string) => clock.format(new Date(iso));

// Value for <input type="datetime-local"> in the browser's time zone.
export function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// Join opens from 15 minutes before the start until the end.
export {joinable} from "../ui/utils";

const day = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
export const formatDay = (iso: string) => day.format(new Date(iso));

// "in 3d", "2h late": how far a due date is from now.
export function dueIn(iso: string, now = Date.now()): string {
  const minutes = Math.round((new Date(iso).getTime() - now) / 60000);
  const late = minutes < 0;
  const m = Math.abs(minutes);
  const span = m < 60 ? `${m}m` : m < 1440 ? `${Math.round(m / 60)}h` : `${Math.round(m / 1440)}d`;
  return late ? `${span} late` : `in ${span}`;
}

export function timeAgo(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
