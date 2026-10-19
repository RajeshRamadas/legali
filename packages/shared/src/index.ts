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

export function createApiClient(baseUrl: string = DEFAULT_API_BASE_URL) {
  return {
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
    chat(message: string, options: ChatOptions = {}): Promise<ChatReply> {
      return request<ChatReply>(baseUrl, "/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, conversation_id: options.conversationId ?? null, history: options.history ?? [], ticket: options.ticket ?? null }),
      });
    },
  };
}
