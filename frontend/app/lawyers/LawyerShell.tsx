"use client";

import "../ui/views/lawyers-lawyers.css";

// Header and footer for Find a lawyer, lawyer profiles and My bookings.
export default function LawyerShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <main>{children}</main>
      <aside className="hx-context-note">
        <div className="wrap hx-tone-78cc9b2f" style={{ fontSize: 11, lineHeight: 1.7 }}>
          Consultations are with independent advocates enrolled with the Bar Council. Booking a consultation does not create a lawyer–client
          relationship for any matter beyond that consultation. Fees are shown up front; a booking cancelled in time is refunded in full.
        </div>
      </aside>
    </>
  );
}
