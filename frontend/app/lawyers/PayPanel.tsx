"use client";

import { useState } from "react";
import { formatFee, paymentLabel, testPayment, type Booking, type BookingRef, type PaymentCheckout } from "@homexo/shared";
import { api } from "../api";

type RazorpayResponse = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };
type RazorpayInstance = { open(): void; on(event: "payment.failed", handler: (r: { error: { description?: string } }) => void): void };
declare global {
  interface Window { Razorpay?: new (options: Record<string, unknown>) => RazorpayInstance }
}

// Razorpay Checkout is loaded only when someone pays.
function loadCheckout(): Promise<NonNullable<Window["Razorpay"]>> {
  if (window.Razorpay) return Promise.resolve(window.Razorpay);
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => (window.Razorpay ? resolve(window.Razorpay) : reject(new Error("Payment window didn't load.")));
    script.onerror = () => reject(new Error("Couldn't load the payment window. Check your connection and try again."));
    document.body.appendChild(script);
  });
}

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });

// The fee on a booking: what's due or paid, and a button that opens Razorpay Checkout (or a pretend payment in test mode).
export default function PayPanel({ bookingRef, booking, onChange }: { bookingRef: BookingRef; booking: Booking; onChange: (b: Booking) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const payment = booking.payment;
  // Nothing to show for an unpaid booking that can no longer be paid (released or cancelled).
  if (!payment || (payment.status === "due" && !payment.can_pay)) return null;

  async function finish(result: Parameters<typeof api.verifyPayment>[1]) {
    try {
      onChange(await api.verifyPayment(bookingRef, result));
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't confirm the payment.");
    } finally {
      setBusy(false);
    }
  }

  async function open(checkout: PaymentCheckout) {
    const Razorpay = await loadCheckout();
    const rzp = new Razorpay({
      key: checkout.key_id, order_id: checkout.order_id, amount: checkout.amount_paise, currency: checkout.currency,
      name: "Homexo Legal", description: checkout.description, prefill: checkout.prefill, theme: { color: "#123b35" },
      handler: (r: RazorpayResponse) => finish({ order_id: r.razorpay_order_id, payment_id: r.razorpay_payment_id, signature: r.razorpay_signature }),
      modal: { ondismiss: () => setBusy(false) },
    });
    rzp.on("payment.failed", (r) => setError(r.error.description || "The payment didn't go through. Try again or use another method."));
    rzp.open();
  }

  async function pay() {
    setError("");
    setBusy(true);
    try {
      const { checkout } = await api.startPayment(bookingRef, "checkout");
      if (checkout.provider === "test") await finish(testPayment(checkout));
      else await open(checkout);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the payment.");
      setBusy(false);
    }
  }

  const due = payment.status === "due";
  return (
    <div className={`lw-pay${due ? " due" : ""}`}>
      <b>{paymentLabel(payment)}</b>
      {due && payment.pay_by && <span>Pay by {time(payment.pay_by)} to keep this time. After that it’s released for others.</span>}
      {payment.status === "paid" && <span>Paid{payment.method ? ` by ${payment.method.toUpperCase()}` : ""}{payment.reference ? ` · ${payment.reference}` : ""}</span>}
      {payment.status === "refund_due" && <span>Refunds reach the original payment method within 5 to 7 working days.</span>}
      {payment.last_error && <span className="lw-pay-error">Last try didn’t go through: {payment.last_error}</span>}
      {error && <span className="lw-pay-error" role="alert">{error}</span>}
      {payment.can_pay && (
        <>
          <button className="btn" onClick={pay} disabled={busy}>
            {busy ? "Opening payment…" : payment.mode === "test" ? `Pay ${formatFee(payment.amount)} (test mode)` : `Pay ${formatFee(payment.amount)} securely`}
          </button>
          <span className="lw-fine">UPI, cards, netbanking and wallets through Razorpay. We never see your card or bank details.</span>
        </>
      )}
    </div>
  );
}
