import os

APP_ENV = os.getenv("APP_ENV", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://homexo_app:change-this-local-password@localhost:5432/homexo")
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]

# Signs staff access tokens. Must be set to a long random value outside development.
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    if APP_ENV != "development":
        raise RuntimeError("JWT_SECRET must be set when APP_ENV is not 'development'.")
    JWT_SECRET = "dev-only-insecure-secret-change-me"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "480"))

# Creates the first admin on startup when no admin exists yet.
BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "")
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_ADMIN_NAME = os.getenv("BOOTSTRAP_ADMIN_NAME", "Homexo Admin")

# AI chat assistant. Without an API key the chat answers from the rule-based topics in chat.py.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Haiku is the low-cost model and is plenty for short answers grounded in retrieved sections.
CHAT_MODEL = os.getenv("CHAT_MODEL", "claude-haiku-5-5")
CHAT_EFFORT = os.getenv("CHAT_EFFORT", "low")
# Server-side refusal fallback re-runs a declined request on another model. Haiku has none, and it is a
# Claude API feature, so keep it "off" on Bedrock, Vertex AI or Foundry.
CHAT_FALLBACKS = os.getenv("CHAT_FALLBACKS", "off" if "haiku" in CHAT_MODEL else "default")
CHAT_RATE_LIMIT_PER_MINUTE = int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "20"))

# Public address of the website, used in links sent to staff (e.g. the calendar in the daily agenda).
PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", "http://localhost:3000").rstrip("/")

# Video consultations. Times in messages and the default working day use this zone.
MEETING_TIMEZONE = os.getenv("MEETING_TIMEZONE", "Asia/Kolkata")
# Minutes before the start when customer and lawyer get a reminder with the join link.
MEETING_REMINDER_MINUTES = sorted({int(m) for m in os.getenv("MEETING_REMINDER_MINUTES", "1440,60,10").split(",") if m.strip()}, reverse=True)
# Local hour (in MEETING_TIMEZONE) when each lawyer gets the day's meetings on WhatsApp. Empty turns it off.
LAWYER_AGENDA_HOUR = int(os.getenv("LAWYER_AGENDA_HOUR", "8") or -1)

# Google Calendar creates the event with a Meet link in a Google Workspace calendar. Use a service account
# with domain-wide delegation for the Calendar scope, acting as GOOGLE_CALENDAR_USER (e.g. meetings@yourdomain).
# GOOGLE_SERVICE_ACCOUNT_JSON is the key file's path or its JSON. Without these, staff paste a meeting link.
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_CALENDAR_USER = os.getenv("GOOGLE_CALENDAR_USER", "")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# WhatsApp Business (Meta Cloud API). Without a token, WhatsApp messages stay queued in the notifications table.
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_BASE = os.getenv("WHATSAPP_API_BASE", "https://graph.facebook.com/v21.0")
WHATSAPP_TEMPLATE_LANGUAGE = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")
# Country code added to 10-digit Indian numbers.
WHATSAPP_DEFAULT_COUNTRY_CODE = os.getenv("WHATSAPP_DEFAULT_COUNTRY_CODE", "91")

# Sends due notifications and queues the daily agenda every NOTIFY_INTERVAL_SECONDS inside the API process.
# Turn off to run `python -m app.notify` from cron or a separate worker instead.
NOTIFY_WORKER_ENABLED = os.getenv("NOTIFY_WORKER_ENABLED", "true").lower() == "true"
NOTIFY_INTERVAL_SECONDS = int(os.getenv("NOTIFY_INTERVAL_SECONDS", "60"))

# Online lawyer bookings. Customers pick from slots in each lawyer's weekly hours, starting this long from now
# and up to BOOKING_DAYS_AHEAD days out. They can cancel or move a booking until CUSTOMER_CHANGE_HOURS before it.
BOOKING_MIN_NOTICE_MINUTES = int(os.getenv("BOOKING_MIN_NOTICE_MINUTES", "120"))
BOOKING_DAYS_AHEAD = int(os.getenv("BOOKING_DAYS_AHEAD", "14"))
CUSTOMER_CHANGE_HOURS = int(os.getenv("CUSTOMER_CHANGE_HOURS", "2"))
# Upcoming online bookings one phone number can hold at a time, so nobody can fill a lawyer's diary.
MAX_UPCOMING_BOOKINGS_PER_PHONE = int(os.getenv("MAX_UPCOMING_BOOKINGS_PER_PHONE", "3"))

# Customer document repository. Files go to an S3-compatible bucket (AWS S3, or Cloudflare R2 with S3_ENDPOINT_URL set
# to https://<account id>.r2.cloudflarestorage.com and S3_REGION=auto) when S3_BUCKET is set, else to LOCAL_STORAGE_DIR.
# Keep the bucket private: downloads go through short-lived signed links. Without S3 keys, boto3's usual chain applies
# (environment, instance role).
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "") or None
S3_REGION = os.getenv("S3_REGION", "") or None
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "") or None
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "") or None
S3_KEY_PREFIX = os.getenv("S3_KEY_PREFIX", "homexo/").lstrip("/")
LOCAL_STORAGE_DIR = os.getenv("LOCAL_STORAGE_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage"))
UPLOAD_MAX_MB = int(os.getenv("UPLOAD_MAX_MB", "25"))
# Files one ticket can hold, so a ticket can't be used as free storage.
MAX_DOCUMENTS_PER_TICKET = int(os.getenv("MAX_DOCUMENTS_PER_TICKET", "200"))
# How long a download link stays valid.
DOWNLOAD_LINK_MINUTES = int(os.getenv("DOWNLOAD_LINK_MINUTES", "15"))
# Printed in the report header and on the PDF footer.
FIRM_NAME = os.getenv("FIRM_NAME", "Homexo Legal")
FIRM_ADDRESS = os.getenv("FIRM_ADDRESS", "Bengaluru, Karnataka")

# Karnataka RERA project pages. Until real data is imported (python -m app.rera_import), the API loads made-up
# sample projects on startup when the table is empty, so the pages have something to show. Set to false in production.
RERA_SAMPLE_WHEN_EMPTY = os.getenv("RERA_SAMPLE_WHEN_EMPTY", "true").lower() == "true"
