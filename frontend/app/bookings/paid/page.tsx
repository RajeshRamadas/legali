import Link from "next/link";
import LawyerShell from "../../lawyers/LawyerShell";

// Razorpay sends customers here after paying on a payment page (the app's payment links).
export default async function PaidPage({ searchParams: query }: { searchParams: Promise<{ razorpay_payment_link_status?: string }> }) {
  const searchParams = await query;
  const paid = searchParams.razorpay_payment_link_status === "paid";
  return (
    <LawyerShell>
      <div className="wrap" style={{ padding: "48px 0", maxWidth: 520 }}>
        <section className="lw-panel lw-done">
          <div className="lw-tick" aria-hidden>{paid ? "✓" : "!"}</div>
          <h2>{paid ? "Payment received" : "Payment not completed"}</h2>
          <p>{paid
            ? "Thank you. Go back to the Homexo app, where My bookings shows the consultation as paid. The details are on their way to your WhatsApp."
            : "Nothing was charged. Go back to the Homexo app and tap Pay again, or try another payment method."}</p>
          <Link className="btn light small" href="/bookings">My bookings on the website</Link>
        </section>
      </div>
    </LawyerShell>
  );
}
