# Video consultations (Google Meet + WhatsApp)

Staff book a "call and discuss" meeting from a ticket. The API creates a Google Calendar event with a Google Meet
link, sends the customer and the lawyer the link on WhatsApp, and reminds both before it starts. Lawyers see their
meetings in **Calendar** in the staff workspace and get the day's list on WhatsApp each morning. Customers see the
meeting, with a Join button, when they track their request.

Everything works without credentials: staff paste a Meet link instead of creating one, and WhatsApp messages wait in
the `notifications` table (visible on the ticket) until WhatsApp is connected.

## How it works

1. On a ticket, **Schedule meeting**: date and time, length, lawyer (agents book themselves; admins pick anyone on
   staff), and an agenda the customer sees. The API rejects times in the past and clashes with the lawyer's other meetings.
2. With Google Calendar connected, the event is created on the Homexo Workspace calendar with a Meet link and both the
   customer (if they gave an email) and the lawyer as guests, so Google emails them the invite and the event appears in
   the lawyer's own Google Calendar. Rescheduling and cancelling update the Google event and Google emails the change.
3. WhatsApp messages are queued for the customer and the lawyer (if a WhatsApp number is set under **Staff**):
   the invite now, then reminders 1 day, 1 hour and 10 minutes before (`MEETING_REMINDER_MINUTES`). Each carries the
   join link. Rescheduling cancels the unsent ones and queues new ones; cancelling sends a cancellation instead.
4. A worker inside the API process (`NOTIFY_WORKER_ENABLED`, every `NOTIFY_INTERVAL_SECONDS`) sends what is due and,
   from `LAWYER_AGENDA_HOUR` (8 am in `MEETING_TIMEZONE`), queues each lawyer's agenda for the meetings still ahead that
   day. A reminder is dropped rather than sent after the start. With several API replicas each message still goes once
   (rows are claimed with `FOR UPDATE SKIP LOCKED`). To run it separately: `NOTIFY_WORKER_ENABLED=false` on the API and
   `python -m app.notify --loop` (or `python -m app.notify` from cron every minute).
5. The lawyer's **Calendar** shows the week (admins can switch between everyone and one lawyer), refreshes every minute,
   and shows a "Time to join" banner from 15 minutes before their next meeting. The customer's tracking card turns its
   button into **Join now** at the same point.

## Connect Google Calendar (Google Workspace)

Meet links can only be created on a Google Workspace user's calendar, so this needs a Workspace account (for example
`meetings@yourdomain.com`) that owns the events.

1. In Google Cloud console, create a project, enable the **Google Calendar API**, and create a **service account**
   with a JSON key.
2. In the Workspace Admin console, **Security → Access and data control → API controls → Domain-wide delegation**,
   add the service account's client ID with the scope `https://www.googleapis.com/auth/calendar.events`.
3. Make sure Google Meet is on for that user's organisational unit.
4. Set on the API:

   ```
   GOOGLE_SERVICE_ACCOUNT_JSON=/run/secrets/google-calendar.json   # or the JSON itself
   GOOGLE_CALENDAR_USER=meetings@yourdomain.com
   GOOGLE_CALENDAR_ID=primary                                       # or a shared calendar's id
   MEETING_TIMEZONE=Asia/Kolkata
   ```

Lawyers whose staff email is a Google account accept the invite once and then see every meeting in Google Calendar on
their phone, with Google's own reminders.

## Connect WhatsApp (Meta WhatsApp Business Cloud API)

1. In Meta Business Manager, set up WhatsApp Business with a phone number and create a **system user** access token
   with `whatsapp_business_messaging` permission.
2. In WhatsApp Manager, create these templates (category **Utility**, language matching `WHATSAPP_TEMPLATE_LANGUAGE`,
   default `en`). Names and the order of placeholders must match; the wording can change before approval.

   | Template name | Body |
   | --- | --- |
   | `meeting_scheduled` | Hi {{1}}, your Homexo Legal consultation on {{2}} is booked for {{3}} with {{4}}. Join on Google Meet: {{5}} |
   | `meeting_rescheduled` | Hi {{1}}, your Homexo Legal consultation on {{2}} has moved to {{3}} with {{4}}. Join on Google Meet: {{5}} |
   | `meeting_reminder` | Hi {{1}}, reminder: your Homexo Legal consultation on {{2}} with {{4}} starts at {{3}}. Tap to join: {{5}} |
   | `meeting_cancelled` | Hi {{1}}, your Homexo Legal consultation on {{2}} at {{3}} with {{4}} has been cancelled. {{5}} |
   | `lawyer_daily_agenda` | Good morning {{1}}, you have {{2}} Homexo Legal consultation(s) today: {{3}}. Your calendar: {{4}} |
   | `urgent_task` | Hi {{1}}, an urgent Homexo Legal task needs you: {{2}}. {{3}} Open it: {{4}} |

   {{1}} is the recipient's name, {{2}} the service and ticket number, {{3}} the time, {{4}} the other person (the
   lawyer for the customer, the customer for the lawyer), {{5}} the Meet link (or the cancellation reason).
   `urgent_task` goes to staff only: {{2}} is the ticket, {{3}} why it's urgent, {{4}} the ticket link.
3. Set on the API:

   ```
   WHATSAPP_ACCESS_TOKEN=...
   WHATSAPP_PHONE_NUMBER_ID=...
   WHATSAPP_DEFAULT_COUNTRY_CODE=91      # added to 10-digit numbers
   PUBLIC_SITE_URL=https://your-site     # link to the calendar in the lawyer's agenda
   ```

Queued messages from before the token was set go out on the next run, except reminders whose meeting has already started.
Failures (for example a number not on WhatsApp) show on the ticket with WhatsApp's error code.

## API

| Method | Path | Who | What |
| --- | --- | --- | --- |
| POST | `/api/v1/admin/tickets/{ticket_number}/meetings` | staff | `{"starts_at", "duration_minutes", "lawyer_id", "agenda", "meet_link"}`. Returns the ticket. Without Google, `meet_link` is required |
| PATCH | `/api/v1/admin/meetings/{id}` | admin or the meeting's lawyer | Reschedule `{"starts_at", "duration_minutes"}`, or `{"status": "cancelled", "reason"}` / `{"status": "completed"}` |
| GET | `/api/v1/admin/meetings?start=&end=&lawyer=` | staff | Calendar window (up to 62 days). `lawyer`: `me`, `all` (admins) or a staff id |

Ticket detail (`meetings`) and the customer's lookup (`meetings`, without staff contact details) include each meeting.
Agents can open tickets where they are the lawyer on a meeting, even when the ticket is assigned to someone else.
