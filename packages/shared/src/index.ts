// Shared by the Next.js website and the Expo mobile app.
// Keep this package free of React, DOM and React Native imports so both can use it.

export type PropertyType =
  | "apartment"
  | "independent_house"
  | "residential_plot"
  | "agricultural_land"
  | "commercial"
  | "other";

export const PROPERTY_TYPES: { value: PropertyType; label: string }[] = [
  { value: "apartment", label: "Apartment" },
  { value: "independent_house", label: "Independent house" },
  { value: "residential_plot", label: "Residential plot" },
  { value: "agricultural_land", label: "Agricultural land" },
  { value: "commercial", label: "Commercial property" },
  { value: "other", label: "Other" },
];

// Mirrors SERVICES in backend/app/catalogue.py.
export type Service = {
  slug: string;
  name: string;
  category: string;
  description: string;
  property_types: PropertyType[];
};

// Mirrors TicketCreate in backend/app/public.py.
export type TicketCreate = {
  customer_name: string;
  contact: string;
  property_type: PropertyType;
  service_slug: string;
  location: string;
  description?: string;
  email?: string;
  package?: string;
  source?: "website" | "chat" | "mobile";
  // The chat this request was raised from, so staff can read it on the ticket.
  conversation_id?: string | null;
};

export type TicketCreated = {
  ticket_number: string;
  status: string;
  message: string;
};

// Mirrors meeting_view in backend/app/tickets.py. meet_link is null once a meeting is cancelled or completed.
export type CustomerMeeting = {
  id: string;
  title: string;
  agenda: string | null;
  starts_at: string;
  ends_at: string;
  when: string;
  status: "scheduled" | "completed" | "cancelled";
  status_label: string;
  lawyer_name: string;
  meet_link: string | null;
};

// Mirrors document_view in backend/app/case_files.py. download_url is a short-lived path on the API; open it with fileUrl().
export type CustomerDocument = {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  tag: string | null;
  note: string | null;
  at: string;
  download_url: string;
  uploaded_by: "you" | "homexo";
  can_delete: boolean;
};

export type GovSource = { key: string; name: string; url: string; search_by: string; automatic: boolean };

export type ReportItemStatus = "pending" | "received" | "verified" | "rejected" | "waived";
// One document the preliminary report asks for. Files tagged with `tag` are linked to it.
export type ReportItem = {
  id: string;
  tag: string;
  label: string;
  guidance: string;
  status: ReportItemStatus;
  status_label: string;
  note: string | null;
  documents: string[];
  // "homexo": a public record the case team gets from a government portal, so the customer needn't upload it.
  fetch_by: "customer" | "homexo";
  source: GovSource | null;
};
export type ReportSection = { key: string; heading: string; hint: string; text: string };

// Mirrors customer_report_view in backend/app/case_files.py. Null until the lawyer issues the preliminary report.
export type CustomerReport = {
  status: "issued" | "final_generated" | "signed";
  status_label: string;
  issued_at: string | null;
  lawyer_name: string | null;
  sections: ReportSection[];
  items: ReportItem[];
  progress: { done: number; total: number };
  preliminary_pdf_url: string;
  signed_report_url: string | null;
  signed_at: string | null;
};

// Mirrors customer_view in backend/app/tickets.py.
export type TicketStatus = {
  ticket_number: string;
  service_name: string;
  package: string | null;
  status: string;
  status_label: string;
  created_at: string;
  history: { status: string; label: string; note: string; at: string }[];
  messages: { from: "you" | "homexo"; message: string; at: string }[];
  meetings: CustomerMeeting[];
  can_reply: boolean;
  documents: CustomerDocument[];
  report: CustomerReport | null;
  can_upload: boolean;
};

// Mirrors the chat endpoint in backend/app/chat.py.
export type ChatTurn = { role: "user" | "assistant"; content: string };
export type ChatTicket = { ticket_number: string; contact: string };
export type ChatOptions = {
  // From the previous reply. Continues the saved conversation, whose transcript is then the history.
  conversationId?: string | null;
  // Earlier turns, oldest first. Only used to start a conversation the server has not saved yet.
  history?: ChatTurn[];
  // A ticket the customer verified in this chat; the server re-checks it on every message.
  ticket?: ChatTicket | null;
};
export type ChatReply = {
  reply: string;
  // "status": the reply is about the verified ticket, which comes back in `ticket`.
  action: "request" | "track" | "status" | null;
  ticket_number: string | null;
  service: Service | null;
  suggestions: string[];
  // Knowledge-base sections an AI answer drew on.
  sources: { title: string; section: string }[];
  mode: "ai" | "rules";
  ticket: TicketStatus | null;
  ticket_verified: boolean;
  conversation_id: string;
};

// Mirrors the card views in backend/app/lawyers.py.
export type LawyerSlot = { starts_at: string; label: string };
export type LawyerCard = {
  slug: string;
  name: string;
  initials: string;
  headline: string;
  specialisations: string[];
  languages: string[];
  experience_years: number;
  // Whole rupees for one consultation.
  consultation_fee: number;
  consultation_minutes: number;
  city: string;
  locality: string | null;
  // Courts the lawyer practises in, e.g. "Karnataka High Court".
  courts: string[];
  rating: number | null;
  review_count: number;
  consultations: number;
  next_available: (LawyerSlot & { day: string }) | null;
};
export type LawyerReview = { rating: number; comment: string; reviewer_name: string; at: string };
export type LawyerProfile = LawyerCard & {
  bio: string;
  // True when the fee is paid online right after booking (Razorpay, or test mode in development).
  pay_online: boolean;
  bar_enrolment: string | null;
  education: string | null;
  hours: { day: string; hours: string[] }[];
  reviews: LawyerReview[];
};
export type LawyerSort = "relevance" | "experience" | "fee_low" | "fee_high" | "rating" | "soonest";
export type LawyerSearch = {
  q?: string;
  specialisation?: string;
  language?: string;
  city?: string;
  max_fee?: number;
  min_experience?: number;
  available?: "today" | "3days";
  sort?: LawyerSort;
};
export type LawyerFilters = {
  specialisations: { value: string; count: number }[];
  languages: { value: string; count: number }[];
  cities: { value: string; count: number }[];
  fee_range: [number, number];
  total: number;
};
export type SlotDay = { date: string; label: string; slots: LawyerSlot[] };
export type BookingCreate = {
  starts_at: string;
  customer_name: string;
  phone: string;
  email?: string;
  issue: string;
  source?: "website" | "mobile";
};
// Mirrors booking_view in backend/app/lawyers.py.
export type Booking = {
  ticket_number: string;
  status: string;
  status_label: string;
  issue: string;
  lawyer: { slug: string | null; name: string; initials: string; headline: string };
  fee: number | null;
  meeting: CustomerMeeting;
  // Moving or cancelling online closes a few hours before the start.
  can_change: boolean;
  can_review: boolean;
  review: LawyerReview | null;
  // Null when the fee isn't paid online (the team arranges payment).
  payment: BookingPayment | null;
};
// Mirrors payment_view in backend/app/payments.py. Amounts in whole rupees.
export type BookingPayment = {
  status: "due" | "paid" | "refund_due" | "refunded";
  amount: number;
  paid_at: string | null;
  method: string | null;
  reference: string | null;
  // An unpaid booking is released at this time.
  pay_by: string | null;
  mode: "razorpay" | "test" | "off";
  can_pay: boolean;
  last_error: string | null;
};
// What the client needs to open Razorpay Checkout (kind "checkout") or the payment page (kind "link").
export type PaymentCheckout = {
  provider: "razorpay" | "test";
  kind: "checkout" | "link";
  order_id: string;
  pay_url: string | null;
  key_id: string | null;
  amount_paise: number;
  currency: string;
  description: string;
  prefill: { name: string; contact: string; email: string };
};
export type PaymentResult = { order_id: string; payment_id: string; signature: string };
// What a customer keeps to find a booking again: the ticket number and the phone or email it was made with.
export type BookingRef = { ticket_number: string; contact: string };

// Customer accounts (backend/app/accounts.py). Customers sign in with a code sent to their phone; the account shows
// everything raised with that number. `contact` is what the ticket, document and booking calls take for these requests.
export type AccountProfile = { name: string | null; phone: string; email: string | null; contact: string };
export type LoginCodeSent = { phone: string; channel: "whatsapp" | "dev"; expires_in: number; resend_after: number; dev_code?: string };
export type AccountSession = { access_token: string; token_type: "bearer"; account: AccountProfile };
export type AccountRequest = {
  ticket_number: string;
  title: string;
  service_name: string;
  package: string | null;
  kind: "consultation" | "request";
  status: string;
  status_label: string;
  created_at: string;
  updated_at: string;
  documents: number;
  report: { status_label: string; progress: { done: number; total: number }; signed: boolean } | null;
  next_meeting: CustomerMeeting | null;
  // A short line when the customer has something to do, e.g. "Documents to upload".
  needs_you: string | null;
};
export type AccountPayment = Pick<BookingPayment, "status" | "amount" | "paid_at" | "method" | "reference" | "can_pay"> & {
  ticket_number: string;
  description: string;
  when: string;
};
export type AccountOverview = {
  profile: AccountProfile;
  requests: AccountRequest[];
  bookings: Booking[];
  payments: AccountPayment[];
  payments_mode: BookingPayment["mode"];
};

export const formatFee = (rupees: number) => `₹${rupees.toLocaleString("en-IN")}`;

// Test mode takes a pretend payment; this id is what the server accepts for it.
export const testPayment = (checkout: PaymentCheckout): PaymentResult => ({
  order_id: checkout.order_id, payment_id: `pay_test_${Date.now().toString(36)}`, signature: "",
});

export const paymentLabel = (payment: Pick<BookingPayment, "status" | "amount">): string => ({
  due: `${formatFee(payment.amount)} to pay`,
  paid: `${formatFee(payment.amount)} paid`,
  refund_due: `Refund of ${formatFee(payment.amount)} on its way`,
  refunded: `${formatFee(payment.amount)} refunded`,
})[payment.status];

export type PostType = "article" | "case_study";

export type PostSummary = {
  id: string;
  slug: string;
  post_type: PostType;
  type_label: string;
  status: "draft" | "published";
  title: string;
  excerpt: string;
  cover_image_url: string | null;
  tags: string[];
  author: string;
  reading_minutes: number;
  published_at: string | null;
  updated_at: string;
};

export type Post = PostSummary & {
  body: string; // Markdown
  highlights: { label: string; value: string }[];
};

export type PublicPost = Post & { related: PostSummary[] };
export type PostList = { items: PostSummary[]; total: number; page: number; page_size: number };
export type PostQuery = { type?: PostType; tag?: string; q?: string; page?: number; pageSize?: number };

// Mirrors the views in backend/app/rera.py.
export type ReraRiskLevel = "green" | "amber" | "red";
export type ReraStatus = "ongoing" | "completed" | "lapsed" | "revoked" | "withdrawn";
export type ReraDataInfo = { projects: number; sample: boolean; updated_at: string | null };
export type ReraProjectCard = {
  registration_no: string;
  slug: string;
  name: string;
  promoter: { name: string; slug: string };
  locality: { name: string; slug: string };
  district: string;
  project_type: string;
  type_label: string;
  status: ReraStatus;
  status_label: string;
  deadline: string | null;
  completed_on: string | null;
  total_units: number | null;
  booked_units: number | null;
  booked_pct: number | null;
  price_per_sqft: number | null;
  delay_months: number | null;
  risk: { level: ReraRiskLevel; label: string; headline: string | null };
  sample: boolean;
};
export type ReraFlag = { level: "amber" | "red"; title: string; detail: string };
export type ReraTrackRecord = {
  projects: number;
  ongoing: number;
  completed: number;
  lapsed_or_revoked: number;
  units: number;
  on_time_pct: number | null;
  avg_delay_months: number | null;
  running_late: number;
  complaints: number;
  verdict: "strong" | "mixed" | "weak" | "new";
  verdict_label: string;
};
export type ReraMarket = {
  projects: number;
  ongoing: number;
  units: number;
  booked_pct: number | null;
  median_price_per_sqft: number | null;
  price_range: [number, number] | null;
  late_pct: number | null;
};
export type ReraSupplyYear = { label: string; projects: number; units: number };
export type ReraRiskCount = { level: ReraRiskLevel; label: string; projects: number };
export type ReraUnitMix = { type: string; units: number }[];
export type ReraProject = Omit<ReraProjectCard, "risk"> & {
  taluk: string | null;
  address: string | null;
  pincode: string | null;
  registered_on: string | null;
  registration_valid_until: string | null;
  proposed_completion: string | null;
  revised_completion: string | null;
  extensions: number;
  unit_mix: ReraUnitMix;
  land_area_sqm: number | null;
  complaints: number;
  source_url: string | null;
  risk: { level: ReraRiskLevel; label: string; flags: ReraFlag[]; good: string[] };
  developer: ReraTrackRecord & { name: string; slug: string };
  locality_market: ReraMarket & { name: string; slug: string };
  developer_projects: ReraProjectCard[];
  nearby: ReraProjectCard[];
  data: ReraDataInfo;
};
export type ReraSummary = {
  data: ReraDataInfo;
  district: string | null;
  as_of: string;
  market: ReraMarket;
  delivery: ReraTrackRecord;
  statuses: { status: ReraStatus; label: string; projects: number }[];
  risk: ReraRiskCount[];
  supply_by_year: ReraSupplyYear[];
  launches_by_year: { year: number; projects: number; units: number }[];
  unit_mix: ReraUnitMix;
  localities: (ReraMarket & { name: string; slug: string; district: string })[];
  developers: (ReraTrackRecord & { name: string; slug: string })[];
};
export type ReraDeveloper = {
  name: string;
  slug: string;
  record: ReraTrackRecord;
  localities: { name: string; slug: string; projects: number }[];
  projects: ReraProjectCard[];
  data: ReraDataInfo;
};
export type ReraLocality = {
  name: string;
  slug: string;
  district: string;
  taluk: string | null;
  market: ReraMarket;
  delivery: ReraTrackRecord;
  risk: ReraRiskCount[];
  supply_by_year: ReraSupplyYear[];
  unit_mix: ReraUnitMix;
  developers: { name: string; slug: string; projects: number; on_time_pct: number | null; verdict: ReraTrackRecord["verdict"]; verdict_label: string }[];
  projects: ReraProjectCard[];
  data: ReraDataInfo;
};
export type ReraFilters = {
  districts: { name: string; projects: number }[];
  localities: { name: string; slug: string; district: string; projects: number }[];
  statuses: { value: ReraStatus; label: string }[];
  types: { value: string; label: string; projects: number }[];
  risk: { value: ReraRiskLevel; label: string }[];
};
export type ReraSort = "name" | "deadline" | "newest" | "units" | "risk" | "price_low";
export type ReraSearch = {
  q?: string;
  district?: string;
  locality?: string;
  promoter?: string;
  status?: ReraStatus;
  type?: string;
  risk?: ReraRiskLevel;
  sort?: ReraSort;
  page?: number;
  page_size?: number;
};
export type ReraSearchResult = { items: ReraProjectCard[]; total: number; page: number; page_size: number; data: ReraDataInfo };

export const DEFAULT_API_BASE_URL = "http://localhost:8000";

// Thrown for any failed API call. status 401 on an account call means the session ended: sign in again.
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    // FastAPI validation errors arrive as a list; show the first one.
    const detail =
      typeof data.detail === "string" ? data.detail
      : Array.isArray(data.detail) && data.detail[0]?.msg ? `${data.detail[0].loc?.at(-1) ?? "Field"}: ${data.detail[0].msg}`
      : "Request failed.";
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// Tags are lowercase words joined by hyphens, e.g. "sale-deed". Mirrors normalize_tag in backend/app/report_templates.py.
export const normalizeTag = (value: string) => value.toLowerCase().replace(/^#/, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);

export const formatBytes = (bytes: number) =>
  bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export function createApiClient(baseUrl: string = DEFAULT_API_BASE_URL) {
  return {
    // Download and report links in ticket views are paths on the API.
    fileUrl(path: string): string {
      return `${baseUrl}${path}`;
    },
    // `file` is a browser File/Blob, or React Native's { uri, name, type }.
    uploadDocument(ref: { ticket_number: string; contact: string }, file: Blob | { uri: string; name: string; type: string }, options: { tag?: string; note?: string; filename?: string } = {}): Promise<TicketStatus> {
      const form = new FormData();
      form.append("ticket_number", ref.ticket_number);
      form.append("contact", ref.contact);
      form.append("tag", options.tag ?? "");
      form.append("note", options.note ?? "");
      if (options.filename) form.append("file", file as Blob, options.filename);
      else form.append("file", file as Blob);
      return request<TicketStatus>(baseUrl, "/api/v1/tickets/documents", { method: "POST", body: form });
    },
    tagDocument(ref: { ticket_number: string; contact: string }, documentId: string, tag: string): Promise<TicketStatus> {
      return request<TicketStatus>(baseUrl, "/api/v1/tickets/documents/tag", post({ ...ref, document_id: documentId, tag }));
    },
    deleteDocument(ref: { ticket_number: string; contact: string }, documentId: string): Promise<TicketStatus> {
      return request<TicketStatus>(baseUrl, "/api/v1/tickets/documents/delete", post({ ...ref, document_id: documentId }));
    },
    listPosts(query: PostQuery = {}): Promise<PostList> {
      const params = new URLSearchParams();
      if (query.type) params.set("type", query.type);
      if (query.tag) params.set("tag", query.tag);
      if (query.q) params.set("q", query.q);
      if (query.page) params.set("page", String(query.page));
      if (query.pageSize) params.set("page_size", String(query.pageSize));
      const qs = params.toString();
      return request<PostList>(baseUrl, `/api/v1/posts${qs ? `?${qs}` : ""}`);
    },
    getPost(slug: string): Promise<PublicPost> {
      return request<PublicPost>(baseUrl, `/api/v1/posts/${encodeURIComponent(slug)}`);
    },
    reraSummary(district?: string): Promise<ReraSummary> {
      return request(baseUrl, `/api/v1/rera/summary${district ? `?district=${encodeURIComponent(district)}` : ""}`);
    },
    reraFilters(): Promise<ReraFilters> {
      return request(baseUrl, "/api/v1/rera/filters");
    },
    searchReraProjects(search: ReraSearch = {}): Promise<ReraSearchResult> {
      const params = new URLSearchParams();
      Object.entries(search).forEach(([key, value]) => value !== undefined && value !== "" && params.set(key, String(value)));
      const qs = params.toString();
      return request(baseUrl, `/api/v1/rera/projects${qs ? `?${qs}` : ""}`);
    },
    getReraProject(slug: string): Promise<ReraProject> {
      return request(baseUrl, `/api/v1/rera/projects/${encodeURIComponent(slug)}`);
    },
    getReraDeveloper(slug: string): Promise<ReraDeveloper> {
      return request(baseUrl, `/api/v1/rera/developers/${encodeURIComponent(slug)}`);
    },
    getReraLocality(slug: string): Promise<ReraLocality> {
      return request(baseUrl, `/api/v1/rera/localities/${encodeURIComponent(slug)}`);
    },
    async listServices(): Promise<Service[]> {
      const data = await request<{ items: Service[] }>(baseUrl, "/api/v1/services");
      return data.items;
    },
    createTicket(payload: TicketCreate): Promise<TicketCreated> {
      return request<TicketCreated>(baseUrl, "/api/v1/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    lookupTicket(ticketNumber: string, contact: string): Promise<TicketStatus> {
      return request<TicketStatus>(baseUrl, "/api/v1/tickets/lookup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket_number: ticketNumber, contact }),
      });
    },
    replyToTicket(ticketNumber: string, contact: string, message: string): Promise<TicketStatus> {
      return request<TicketStatus>(baseUrl, "/api/v1/tickets/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket_number: ticketNumber, contact, message }),
      });
    },
    searchLawyers(search: LawyerSearch = {}): Promise<{ items: LawyerCard[]; total: number }> {
      const params = Object.entries(search)
        .filter(([, value]) => value !== undefined && value !== "")
        .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
        .join("&");
      return request(baseUrl, `/api/v1/lawyers${params ? `?${params}` : ""}`);
    },
    lawyerFilters(): Promise<LawyerFilters> {
      return request(baseUrl, "/api/v1/lawyers/filters");
    },
    getLawyer(slug: string): Promise<LawyerProfile> {
      return request(baseUrl, `/api/v1/lawyers/${encodeURIComponent(slug)}`);
    },
    lawyerSlots(slug: string, days = 7): Promise<{ days: SlotDay[]; minutes: number; timezone: string }> {
      return request(baseUrl, `/api/v1/lawyers/${encodeURIComponent(slug)}/slots?days=${days}`);
    },
    bookLawyer(slug: string, payload: BookingCreate): Promise<Booking> {
      return request(baseUrl, `/api/v1/lawyers/${encodeURIComponent(slug)}/bookings`, post(payload));
    },
    lookupBooking(ref: BookingRef): Promise<Booking> {
      return request(baseUrl, "/api/v1/bookings/lookup", post(ref));
    },
    cancelBooking(ref: BookingRef, reason?: string): Promise<Booking> {
      return request(baseUrl, "/api/v1/bookings/cancel", post({ ...ref, reason: reason || null }));
    },
    rescheduleBooking(ref: BookingRef, startsAt: string): Promise<Booking> {
      return request(baseUrl, "/api/v1/bookings/reschedule", post({ ...ref, starts_at: startsAt }));
    },
    reviewBooking(ref: BookingRef, rating: number, comment: string): Promise<Booking> {
      return request(baseUrl, "/api/v1/bookings/review", post({ ...ref, rating, comment }));
    },
    startPayment(ref: BookingRef, kind: PaymentCheckout["kind"] = "checkout"): Promise<{ booking: Booking; checkout: PaymentCheckout }> {
      return request(baseUrl, "/api/v1/bookings/pay", post({ ...ref, kind }));
    },
    verifyPayment(ref: BookingRef, result: PaymentResult): Promise<Booking> {
      return request(baseUrl, "/api/v1/bookings/pay/verify", post({ ...ref, ...result }));
    },
    refreshPayment(ref: BookingRef): Promise<Booking> {
      return request(baseUrl, "/api/v1/bookings/pay/refresh", post(ref));
    },
    startLogin(phone: string): Promise<LoginCodeSent> {
      return request(baseUrl, "/api/v1/account/login/start", post({ phone }));
    },
    verifyLogin(phone: string, code: string): Promise<AccountSession> {
      return request(baseUrl, "/api/v1/account/login/verify", post({ phone, code }));
    },
    getAccount(token: string): Promise<AccountOverview> {
      return request(baseUrl, "/api/v1/account", { headers: bearer(token) });
    },
    getAccountRequest(token: string, ticketNumber: string): Promise<TicketStatus> {
      return request(baseUrl, `/api/v1/account/requests/${encodeURIComponent(ticketNumber)}`, { headers: bearer(token) });
    },
    updateAccount(token: string, changes: { full_name?: string; email?: string }): Promise<AccountProfile> {
      return request(baseUrl, "/api/v1/account", { method: "PATCH", headers: { ...bearer(token), "Content-Type": "application/json" }, body: JSON.stringify(changes) });
    },
    signOutEverywhere(token: string): Promise<{ ok: boolean }> {
      return request(baseUrl, "/api/v1/account/logout-all", { method: "POST", headers: bearer(token) });
    },
    chat(message: string, options: ChatOptions = {}): Promise<ChatReply> {
      return request<ChatReply>(baseUrl, "/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, conversation_id: options.conversationId ?? null, history: options.history ?? [], ticket: options.ticket ?? null }),
      });
    },
  };
}
