# Find a lawyer and book a consultation

A Practo-style flow for lawyers, on the website (`/lawyers`, `/lawyers/{slug}`, `/bookings`) and in the mobile app (Find a lawyer and My bookings tabs).

## Customers

1. **Search.** Listed lawyers can be filtered by specialisation, language, city, maximum fee, minimum experience and availability (today or the next 3 days), searched by free text (name, headline, specialisation, language, area) and sorted by relevance, soonest slot, rating, experience or fee. Each card shows the fee, rating, experience, languages, area and the next open slot.
2. **Profile.** About, credentials (education, Bar enrolment, courts), fee and length, weekly hours and reviews.
3. **Book.** The customer picks a day and an open slot, then gives their name, WhatsApp number, optional email and what they want to discuss. The booking:
   - creates a ticket for the Advocate Consultation service, assigned to the lawyer (status "Case team assigned");
   - adds a meeting on that ticket, so it gets a Google Meet link when Google Calendar is connected, WhatsApp invites and reminders for both sides, and appears on the lawyer's calendar (`docs/meetings.md`);
   - returns the booking number (the ticket number). The website remembers it in the browser and the app on the phone.
4. **My bookings.** Lists bookings made on that browser or phone, and finds others by booking number plus the phone or email used. Customers can join (the link is shown while the meeting is on), reschedule to another open slot or cancel until `CUSTOMER_CHANGE_HOURS` before the start, and rate the consultation once after it has ended. A cancelled online booking also cancels its ticket.

Without Google Calendar, a booking has no link at first. The WhatsApp invite says the link will follow, and staff add it from the ticket page (**Add meeting link**), which sends it to both sides and updates the queued reminders.

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

## Safeguards

- Bookings are checked against the lawyer's open slots at the moment of booking, and the lawyer's row is locked while checking (PostgreSQL), so two customers can't take the same slot.
- Managing a booking needs both the booking number and the phone or email used, and the API gives the same answer for a wrong number or a wrong contact.
- Reviews are tied to a meeting that has ended, one per meeting, and show the reviewer as first name and initial.

## Not built yet

- Online payment of the fee. The fee is shown and saved on the ticket; the team confirms payment before the call.
- Customer accounts with OTP. Until then, My bookings relies on the booking number plus phone or email.
- Moderating or replying to reviews, verified-lawyer badges, lawyer photos, and clinic-style in-person appointments.
- Rate limiting on booking and lookup beyond the per-phone cap.

Sample data for development: `cd backend && python -m app.demo_lawyers` adds six listed sample lawyers.
