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

// Mirrors SERVICES in backend/app/main.py.
export type Service = {
  slug: string;
  name: string;
  category: string;
  description: string;
  property_types: PropertyType[];
};

// Mirrors TicketCreate in backend/app/main.py.
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
};

export type TicketCreated = {
  ticket_number: string;
  status: string;
  message: string;
};

// Mirrors _public_ticket in backend/app/main.py.
export type TicketStatus = {
  ticket_number: string;
  service_name: string;
  package: string | null;
  status: string;
  status_label: string;
  created_at: string;
  history: { status: string; label: string; note: string; at: string }[];
};

// Mirrors the chat endpoint in backend/app/main.py.
export type ChatReply = {
  reply: string;
  action: "request" | "track" | null;
  ticket_number: string | null;
  service: Service | null;
  suggestions: string[];
};

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
    chat(message: string): Promise<ChatReply> {
      return request<ChatReply>(baseUrl, "/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
    },
  };
}
