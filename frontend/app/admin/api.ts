import { DEFAULT_API_BASE_URL } from "@homexo/shared";

// Staff workspace API (backend/app/admin.py). Kept out of @homexo/shared because only the website uses it.
const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;
const TOKEN_KEY = "homexo.staff.token";

export type StaffUser = { id: string; name: string; email: string | null; role: "admin" | "agent"; account_status?: string };
export type StaffRef = { id: string; name: string } | null;

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

export type TicketDetail = TicketSummary & {
  description: string;
  customer: { id: string; name: string; phone: string | null; email: string | null };
  property: { type: string; location: string | null } | null;
  events: { type: string; old: Record<string, string> | null; new: Record<string, string> | null; note: string | null; actor: StaffRef; at: string }[];
  messages: { id: string; author_type: "customer" | "staff" | "system"; author: StaffRef; visibility: "customer" | "internal"; message: string; at: string }[];
  notifications: { channel: string; template: string; recipient: string | null; status: string; at: string }[];
};

export type Summary = { open: number; new_today: number; unassigned: number; needs_reply: number; by_status: { status: string; label: string; count: number }[] };
export type Meta = { statuses: { value: string; label: string }[]; priorities: string[] };

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

const dateTime = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export const formatDate = (iso: string) => dateTime.format(new Date(iso));

export function timeAgo(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
