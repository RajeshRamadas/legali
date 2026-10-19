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
  rating: number | null;
  review_count: number;
  consultations: number;
  next_available: (LawyerSlot & { day: string }) | null;
};
export type LawyerReview = { rating: number; comment: string; reviewer_name: string; at: string };
export type LawyerProfile = LawyerCard & {
  bio: string;
  courts: string[];
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
};
// What a customer keeps to find a booking again: the ticket number and the phone or email it was made with.
export type BookingRef = { ticket_number: string; contact: string };

export const formatFee = (rupees: number) => `₹${rupees.toLocaleString("en-IN")}`;

export const DEFAULT_API_BASE_URL = "http://localhost:8000";

async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    // FastAPI validation errors arrive as a list; show the first one.
    const detail =
      typeof data.detail === "string" ? data.detail
      : Array.isArray(data.detail) && data.detail[0]?.msg ? `${data.detail[0].loc?.at(-1) ?? "Field"}: ${data.detail[0].msg}`
      : "Request failed.";
    throw new Error(detail);
  }
  return data as T;
}

const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function createApiClient(baseUrl: string = DEFAULT_API_BASE_URL) {
  return {
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
    chat(message: string, options: ChatOptions = {}): Promise<ChatReply> {
      return request<ChatReply>(baseUrl, "/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, conversation_id: options.conversationId ?? null, history: options.history ?? [], ticket: options.ticket ?? null }),
      });
    },
  };
}
