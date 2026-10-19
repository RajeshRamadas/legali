import type { BookingRef } from "@homexo/shared";

// Bookings made or found on this browser, so My bookings can list them without an account.
// Storage can be unavailable (private mode, blocked site data), so every access is guarded.
const KEY = "homexo.bookings";

export function savedBookings(): BookingRef[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(value) ? value.filter((r) => r && typeof r.ticket_number === "string" && typeof r.contact === "string") : [];
  } catch {
    return [];
  }
}

export function saveBooking(ref: BookingRef): void {
  try {
    const others = savedBookings().filter((r) => r.ticket_number !== ref.ticket_number);
    localStorage.setItem(KEY, JSON.stringify([ref, ...others].slice(0, 20)));
  } catch {
    // Not remembered on this browser; the customer can still find it with the ticket number.
  }
}

export function forgetBooking(ticketNumber: string): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(savedBookings().filter((r) => r.ticket_number !== ticketNumber)));
  } catch {
    // Nothing stored to remove.
  }
}
