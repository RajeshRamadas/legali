"""Offline deployment policy. Never connects to services or returns configuration values."""
import ipaddress
import re
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ENVIRONMENTS = frozenset({"development", "test", "performance", "staging", "production"})
DEPLOYED_ENVIRONMENTS = frozenset({"staging", "production"})
PLACEHOLDERS = ("change-this", "change-me", "changeme", "replace-me", "replace-with", "dev-only", "ci-only", "example-secret")


def placeholder(value):
    return any(marker in value.lower().replace("_", "-") for marker in PLACEHOLDERS)


def secret_configured(value, minimum=32):
    return (isinstance(value, str) and len(value) >= minimum and len(set(value)) >= 8
        and not placeholder(value))


def https_origin(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        if (url.scheme != "https" or not host or url.username is not None or url.password is not None
            or url.path not in ("", "/") or url.query or url.fragment or url.port == 0
            or any(char.isspace() for char in value) or "\\" in value or "*" in value or "%" in host):
            return None
        if (host == "localhost" or host.endswith((".localhost", ".invalid", ".example"))
            or host in {"example.com", "example.org", "example.net"}):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_loopback or address.is_unspecified):
            return None
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped and (mapped.is_loopback or mapped.is_unspecified):
            return None
        if address:
            host = str(address)
        else:
            host = host.encode("idna").decode("ascii")
            labels = host.split(".")
            if (len(labels) < 2 or labels[-1].isdigit() or len(host) > 253
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", item) for item in labels)):
                return None
        display_host = f"[{host}]" if ":" in host else host
        return f"https://{display_host}" + (f":{url.port}" if url.port not in (None, 443) else "")
    except (TypeError, ValueError):
        return None


def inspect_environment(source, target):
    """Inspect an explicit staging/production target; inputs are read-only and output is fixed text."""
    if target not in DEPLOYED_ENVIRONMENTS:
        raise ValueError("Select staging or production as the deployment target.")
    checks = []

    def record(identifier, passed, message):
        checks.append({"id": identifier, "status": "pass" if passed else "fail", "message": message})

    def warn(identifier, message):
        checks.append({"id": identifier, "status": "warning", "message": message})

    record("environment", source.get("APP_ENV") == target, "APP_ENV must match the selected staging or production target.")
    jwt = source.get("JWT_SECRET", "")
    record("jwt_secret", secret_configured(jwt), "JWT_SECRET needs a unique random value of at least 32 characters; development/placeholder values are refused.")
    mfa = source.get("STAFF_MFA_ENCRYPTION_KEY", "")
    try:
        Fernet(mfa.encode())
        mfa_valid = mfa != jwt and secret_configured(mfa)
    except (ValueError, TypeError, UnicodeError):
        mfa_valid = False
    record("mfa_key", mfa_valid, "STAFF_MFA_ENCRYPTION_KEY must be a separate valid Fernet key.")

    # Match config.py's boolean semantics; reject misspellings rather than silently disabling protection.
    for name, expected, default in (
        ("STAFF_REQUIRE_ADMIN_MFA", True, "true"),
        ("LOGIN_CODE_DEV_MODE", False, "false"),
        ("PAYMENTS_TEST_MODE", False, "false"),
        ("RERA_SAMPLE_WHEN_EMPTY", False, "true"),
    ):
        raw = source.get(name, default)
        if name == "STAFF_REQUIRE_ADMIN_MFA" and not raw:
            raw = default
        value = raw.lower()
        good = value in ("true", "false") and (value == "true") == expected
        record(name.lower(), good, f"{name} must resolve to {'true' if expected else 'false'} outside development.")

    try:
        url = make_url(source.get("DATABASE_URL", ""))
        passwords = [url.password, url.query.get("password")]
        database_valid = (url.drivername in ("postgresql", "postgresql+psycopg") and bool(url.host and url.database)
            and all(value is None or (isinstance(value, str) and bool(value) and not placeholder(value)
                and value.lower() not in ("password", "postgres", "secret")) for value in passwords))
    except (ArgumentError, ValueError, TypeError):
        database_valid = False
    record("database", database_valid, "DATABASE_URL must explicitly select PostgreSQL and omit development/placeholder passwords.")
    warn("database_transport", "Verify database TLS, least-privilege access and network isolation with the deployment operator; this offline check does not connect.")

    site = https_origin(source.get("PUBLIC_SITE_URL", ""))
    origins = [item.strip() for item in source.get("CORS_ORIGINS", "").split(",") if item.strip()]
    normalized = [https_origin(item) for item in origins]
    record("public_site", bool(site), "PUBLIC_SITE_URL must be a real HTTPS origin without credentials, path, query or fragment.")
    record("cors", bool(origins) and all(normalized) and site in normalized,
        "CORS_ORIGINS must contain explicit HTTPS origins, including PUBLIC_SITE_URL; wildcards and local/example origins are refused.")

    email, password = source.get("BOOTSTRAP_ADMIN_EMAIL", ""), source.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    bootstrap_valid = not email and not password
    if email and password:
        bootstrap_valid = (bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))
            and email.lower() != "admin@homexo.local" and bool(https_origin("https://" + email.rsplit("@", 1)[-1]))
            and secret_configured(password, 12))
        if bootstrap_valid:
            warn("bootstrap_cleanup", "Remove bootstrap credentials from the deployment after the first administrator is established.")
    record("bootstrap", bootstrap_valid, "Bootstrap administrator settings must be absent together or use a real email and unique password of at least 12 characters.")

    key, payment_secret, webhook = (source.get(name, "") for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"))
    if any((key, payment_secret, webhook)):
        prefix = "rzp_live_" if target == "production" else "rzp_test_"
        record("payments", key.startswith(prefix) and len(key) > len(prefix) and secret_configured(payment_secret, 20) and secret_configured(webhook, 24),
            "Configured Razorpay requires a complete key/secret/webhook set; staging uses test keys and production uses live keys.")
    else:
        checks.append({"id": "payments", "status": "pass", "message": "Online payments are disabled when provider keys and test mode are absent."})

    bucket = source.get("S3_BUCKET", "")
    access, private = source.get("S3_ACCESS_KEY_ID", ""), source.get("S3_SECRET_ACCESS_KEY", "")
    endpoint = source.get("S3_ENDPOINT_URL", "")
    record("storage_credentials", bool(access) == bool(private) and (not (access or private or endpoint) or bool(bucket)),
        "S3 settings must select a bucket and supply access/secret keys together, or use the runtime IAM credential chain.")
    if endpoint:
        record("storage_endpoint", bool(https_origin(endpoint)), "A custom S3_ENDPOINT_URL must be an HTTPS origin without embedded credentials.")
    if bucket:
        warn("storage_policy", "Verify bucket privacy, encryption, permissions and backup coverage; credentials and bucket policy are not probed.")
    else:
        warn("local_storage", "Local document storage needs a durable private volume and tested encrypted backups; no durability check is performed.")
    whatsapp = [bool(source.get(name)) for name in ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID")]
    record("whatsapp_credentials", all(whatsapp) or not any(whatsapp), "WhatsApp token and phone-number ID must be configured together.")
    if not all(whatsapp):
        warn("customer_signin", "Customer phone sign-in is unavailable without WhatsApp credentials and an approved authentication template.")
    else:
        warn("customer_signin", "Verify WhatsApp authentication-template approval and code delivery with a controlled account before launch.")
    warn("operations", "Verify migrations, scanner/signatures, workers, alert routing, backups/recovery and legal/support owners separately; this is configuration validation only.")
    failures = sum(item["status"] == "fail" for item in checks)
    return {"version": 1, "target": target, "configuration_passed": failures == 0, "failures": failures,
        "warnings": sum(item["status"] == "warning" for item in checks), "checks": checks}


def startup_errors(source):
    """Enforce deployed policy before any database bootstrap or background workers start."""
    environment = source.get("APP_ENV", "development")
    if environment not in ENVIRONMENTS:
        return ["environment"]
    if environment not in DEPLOYED_ENVIRONMENTS:
        return []
    return [item["id"] for item in inspect_environment(source, environment)["checks"] if item["status"] == "fail"]
