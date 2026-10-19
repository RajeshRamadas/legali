# Find a lawyer and book a consultation

A Practo-style flow for lawyers, on the website (`/lawyers`, `/lawyers/{slug}`, `/bookings`) and in the mobile app (Find a lawyer and My bookings tabs).

## Customers

1. **Search.** Listed lawyers can be filtered by specialisation, language, city, maximum fee, minimum experience and availability (today or the next 3 days), searched by free text (name, headline, specialisation, language, area) and sorted by relevance, soonest slot, rating, experience or fee. Each card shows the name, specialisations, years of experience, the courts they practise in, languages, area, rating, fee and the next open slot. Free text also matches courts ("high court").
2. **Profile.** About, credentials (education, Bar enrolment, courts), fee and length, weekly hours and reviews.
3. **Book.** The customer picks a day and an open slot, then gives their name, WhatsApp number, optional email and what they want to discuss. The booking:
   - creates a ticket for the Advocate Consultation service, assigned to the lawyer (status "Case team assigned");
   - adds a meeting on that ticket, so it gets a Google Meet link when Google Calendar is connected, WhatsApp invites and reminders for both sides, and appears on the lawyer's calendar (`docs/meetings.md`);
   - returns the booking number (the ticket number). The website remembers it in the browser and the app on the phone.
4. **Pay.** When online payment is on, the slot is held and the customer pays the fee straight away (see Payment below). An unpaid booking is released after `PAYMENT_HOLD_MINUTES`.
5. **My bookings.** Lists bookings made on that browser or phone, and finds others by booking number plus the phone or email used. Customers can pay a fee still due, join (the link is shown while the meeting is on), reschedule to another open slot or cancel until `CUSTOMER_CHANGE_HOURS` before the start, and rate the consultation once after it has ended. A cancelled online booking also cancels its ticket.

Without Google Calendar, a booking has no link at first. The WhatsApp invite says the link will follow, and staff add it from the ticket page (**Add meeting link**), which sends it to both sides and updates the queued reminders.

## Payment

The fee is paid online through Razorpay, so customers can use UPI, cards, netbanking or wallets. Card and bank details stay with Razorpay; we keep its order and payment ids and the outcome (`payments` table).

- **Website:** the server creates a Razorpay order and the page opens Razorpay Checkout. Checkout's success handler posts the order id, payment id and signature to `/api/v1/bookings/pay/verify`, and the server checks the signature (HMAC-SHA256 of `order_id|payment_id` with the key secret) before counting it.
- **App:** the server creates a Razorpay payment link and the app opens it in the browser. When the customer comes back, the app asks the server, which checks the link's status with Razorpay. Razorpay's own redirect lands on `/bookings/paid`.
- **Webhook:** point a Razorpay webhook at `https://<api>/api/v1/payments/razorpay/webhook` with the events `order.paid`, `payment_link.paid`, `payment.failed` and `refund.processed`, and set its secret as `RAZORPAY_WEBHOOK_SECRET`. It catches payments whose page was closed before returning, records failures (shown to the customer so they can try another way) and marks refunds.
- **Holding the slot:** a booking made with online payment holds its slot for `PAYMENT_HOLD_MINUTES` (30 by default). The notification worker then cancels it if the fee is still unpaid, frees the slot and tells the customer on WhatsApp. It checks with Razorpay first, so a payment whose webhook is late isn't dropped.
- **Refunds:** cancelling a paid booking in time (customer or staff), or a payment arriving after a booking was released or twice, marks the payment "refund due" on the ticket timeline. Staff refund it from the Razorpay dashboard (Payments, then Refund); the `refund.processed` webhook then marks it refunded.
- **Staff view:** payments, failures and refunds appear in the ticket's activity, with the Razorpay payment id.

Payment modes:

| Mode | When | What happens |
| --- | --- | --- |
| Razorpay | `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are set | Real Checkout and payment links. Use `rzp_test_` keys to try it without real money. |
| Test | No keys, and `PAYMENTS_TEST_MODE` is true (the default when `APP_ENV=development`) | A "Pay (test mode)" button marks the fee paid without any provider. Never enable this in production. |
| Off | No keys and test mode off | As before: the fee is shown and saved on the ticket, and the team arranges payment. |

Bookings made before payment was switched on, or while it was off, are not asked to pay and are never released.

## Lawyers and admins

Every staff member can open **Lawyer profile** in `/admin` to edit their headline, about text, education, Bar enrolment, courts, specialisations, languages, experience, city and area, fee, consultation length and weekly hours, then **Save and go live**. A profile needs a headline, a specialisation, a language and some hours before it can be listed. Admins can pick any staff member and edit or hide their profile.

Slots are the weekly hours cut into consultation-length pieces, in `MEETING_TIMEZONE`. Anything already on the lawyer's calendar (online bookings and meetings staff scheduled) is blocked out, so staff keep booking meetings from tickets as before.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `BOOKING_MIN_NOTICE_MINUTES` | 120 | Earliest slot offered, counted from now |
| `BOOKING_DAYS_AHEAD` | 14 | How far ahead customers can book |
| `CUSTOMER_CHANGE_HOURS` | 2 | Customers can move or cancel online until this many hours before the start |
| `MAX_UPCOMING_BOOKINGS_PER_PHONE` | 3 | Upcoming online bookings one phone number can hold |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | empty | Razorpay API keys (Dashboard, then Account & Settings, then API keys). Keep them in the environment, never in the repository. |
| `RAZORPAY_WEBHOOK_SECRET` | empty | The secret set on the Razorpay webhook. Without it the webhook answers 503. |
| `PAYMENTS_TEST_MODE` | true in development, else false | Pretend payments when no keys are set |
| `PAYMENT_HOLD_MINUTES` | 30 | How long an unpaid booking holds its slot. 0 keeps unpaid bookings. |

## Team calls and urgent tasks

- **Team calls** (`/admin/team`, plus the switch under your name in the sidebar): each staff member says whether the team can phone them now, with an optional note such as "Till 6 pm", and sets their own mobile number. Everyone on the team sees who is available, with a Call button.
- **Urgent tasks:** when staff set a ticket's priority to Urgent they can say why (team only). The assignee gets a WhatsApp alert (`urgent_task` template, see `docs/meetings.md`) with the reason and a link, and the ticket shows under Urgent at the top of their queue. Assigning an urgent ticket to someone alerts them too. Marking your own ticket urgent alerts nobody.
- **Lawyers' numbers stay private:** customers only ever see a lawyer's name. Booking pages, the public API, meeting invites and reminders carry no staff phone number, and WhatsApp messages come from the Homexo business number. A test checks every customer-facing response and message for it.

## Safeguards

- Bookings are checked against the lawyer's open slots at the moment of booking, and the lawyer's row is locked while checking (PostgreSQL), so two customers can't take the same slot.
- Managing a booking needs both the booking number and the phone or email used, and the API gives the same answer for a wrong number or a wrong contact.
- Reviews are tied to a meeting that has ended, one per meeting, and show the reviewer as first name and initial.

## Not built yet

- Refunds from inside the staff workspace (staff refund in the Razorpay dashboard for now), GST invoices, and coupons.
- Customer accounts with OTP. Until then, My bookings relies on the booking number plus phone or email.
- Moderating or replying to reviews, verified-lawyer badges, lawyer photos, and clinic-style in-person appointments.
- Rate limiting on booking and lookup beyond the per-phone cap.

Sample data for development: `cd backend && python -m app.demo_lawyers` adds six listed sample lawyers.
