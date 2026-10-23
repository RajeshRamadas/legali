# Customer accounts

Customers sign in with their phone number and a 6-digit code, then see every request, consultation booking, payment
and case document raised with that number, on the website (`/account`) and in the app (Account tab).

## How it works

- `POST /api/v1/account/login/start {phone}` sends a code; `POST /api/v1/account/login/verify {phone, code}` returns a
  session token (30 days, `CUSTOMER_SESSION_DAYS`). Tokens are separate from staff tokens and can't be used in `/admin`.
- An account is keyed by the last 10 digits of the phone. Tickets and bookings made before signing up, with the same
  number, show up straight away. Requests raised with only an email don't link.
- `GET /api/v1/account` lists requests, bookings and payments; `GET /api/v1/account/requests/{ticket}` returns one ticket.
  `PATCH /api/v1/account` edits name and email; `POST /api/v1/account/logout-all` signs out every device.
- Signed-in clients keep using the existing ticket, document and booking endpoints with the account's verified phone
  (`profile.contact`) as the contact.

## Limits

Codes last 10 minutes, allow 5 tries, and only the newest one works. One number can ask for 5 codes an hour and one
address for 20, with 30 seconds between codes. Only a keyed hash of each code is stored. All of these are settings in
`backend/app/config.py`.

## Delivering codes

Codes go out on WhatsApp through the existing Meta Cloud API settings (`WHATSAPP_ACCESS_TOKEN`,
`WHATSAPP_PHONE_NUMBER_ID`). Create an **Authentication** template named `login_code` (or set `LOGIN_CODE_TEMPLATE`)
with a copy-code button; the code fills both the body and the button.

Without WhatsApp credentials, dev mode (`LOGIN_CODE_DEV_MODE`, on only when `APP_ENV=development`) shows the code on
screen and in the API log. With neither, sign-in answers that it isn't available and customers track requests by
ticket number as before. There is no SMS provider yet.
