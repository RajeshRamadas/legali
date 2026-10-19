import { useEffect, useState } from "react";
import { AppState, Linking, Pressable, Text, View } from "react-native";
import { formatFee, paymentLabel, testPayment, type Booking, type BookingRef } from "@homexo/shared";
import { styles } from "./LawyersScreen";
import { ui } from "./lawyerUi";
import { api, colors } from "./theme";

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });

// The fee on a booking: pays through a Razorpay payment page in the browser and checks the result on return.
export function PayPanel({ bookingRef, booking, onChange }: { bookingRef: BookingRef; booking: Booking; onChange: (b: Booking) => void }) {
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState("");
  const payment = booking.payment;

  async function check() {
    setError("");
    try {
      onChange(await api.refreshPayment(bookingRef));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not check the payment.");
    }
  }

  // Back from the payment page: ask whether it went through.
  useEffect(() => {
    if (!waiting) return;
    const sub = AppState.addEventListener("change", (state) => { if (state === "active") check(); });
    return () => sub.remove();
  }, [waiting]);

  useEffect(() => {
    if (payment?.status !== "due") setWaiting(false);
  }, [payment?.status]);

  // Nothing to show for an unpaid booking that can no longer be paid (released or cancelled).
  if (!payment || (payment.status === "due" && !payment.can_pay)) return null;

  async function pay() {
    setError("");
    setBusy(true);
    try {
      const { checkout } = await api.startPayment(bookingRef, "link");
      if (checkout.provider === "test") {
        onChange(await api.verifyPayment(bookingRef, testPayment(checkout)));
      } else if (checkout.pay_url) {
        setWaiting(true);
        await Linking.openURL(checkout.pay_url);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the payment.");
    } finally {
      setBusy(false);
    }
  }

  const due = payment.status === "due";
  return (
    <View style={[styles.summary, !due && { backgroundColor: "#f3f5f1" }]}>
      <Text style={[styles.summaryValue, due && { color: colors.danger }]}>{paymentLabel(payment)}</Text>
      {due && payment.pay_by && <Text style={ui.muted}>Pay by {time(payment.pay_by)} to keep this time. After that it's released for others.</Text>}
      {payment.status === "paid" && <Text style={ui.muted}>Paid{payment.method ? ` by ${payment.method.toUpperCase()}` : ""}{payment.reference ? ` · ${payment.reference}` : ""}</Text>}
      {payment.status === "refund_due" && <Text style={ui.muted}>Refunds reach the original payment method within 5 to 7 working days.</Text>}
      {payment.last_error ? <Text style={ui.error}>Last try didn't go through: {payment.last_error}</Text> : null}
      {error ? <Text style={ui.error}>{error}</Text> : null}
      {payment.can_pay && (
        <View style={{ gap: 8, marginTop: 6 }}>
          <Pressable style={[styles.button, busy && { opacity: 0.5 }]} disabled={busy} onPress={pay}>
            <Text style={styles.buttonText}>{busy ? "Opening…" : payment.mode === "test" ? `Pay ${formatFee(payment.amount)} (test mode)` : `Pay ${formatFee(payment.amount)} securely`}</Text>
          </Pressable>
          {waiting
            ? <Pressable onPress={check} hitSlop={8}><Text style={styles.link}>I've paid, check again</Text></Pressable>
            : <Text style={styles.small}>UPI, cards, netbanking and wallets through Razorpay. We never see your card or bank details.</Text>}
        </View>
      )}
    </View>
  );
}
