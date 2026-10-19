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
