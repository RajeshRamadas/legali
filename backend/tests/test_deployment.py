"""Deployment policy must reject unsafe settings without connecting or exposing their values."""
import json
from pathlib import Path
import secrets
import subprocess
import sys

from cryptography.fernet import Fernet
import pytest

from app.deployment import https_origin, inspect_environment, startup_errors

ROOT = Path(__file__).resolve().parents[2]


def settings(target="production"):
    return {"APP_ENV": target, "DATABASE_URL": "postgresql+psycopg://app:unit-password-only@db/deployment_fixture",
        "JWT_SECRET": secrets.token_urlsafe(48), "STAFF_MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "STAFF_REQUIRE_ADMIN_MFA": "true", "LOGIN_CODE_DEV_MODE": "false", "PAYMENTS_TEST_MODE": "false",
        "RERA_SAMPLE_WHEN_EMPTY": "false", "PUBLIC_SITE_URL": "https://legal.deployment.test",
        "CORS_ORIGINS": "https://legal.deployment.test"}


def failures(source, target="production"):
    return {item["id"] for item in inspect_environment(source, target)["checks"] if item["status"] == "fail"}


def test_valid_profiles_are_offline_read_only_and_keep_manual_checks_visible(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Offline checks contacted a service"))
    for target in ("staging", "production"):
        source = settings(target); original = dict(source)
        report = inspect_environment(source, target)
        assert report["configuration_passed"] and report["failures"] == 0
        assert report["warnings"] >= 4 and source == original and startup_errors(source) == []
        assert "customer_signin" in {item["id"] for item in report["checks"] if item["status"] == "warning"}


@pytest.mark.parametrize("name,value,identifier", [
    ("APP_ENV", "prod", "environment"), ("APP_ENV", "development", "environment"),
    ("JWT_SECRET", "dev-only-insecure-secret-change-me", "jwt_secret"),
    ("JWT_SECRET", "a" * 80, "jwt_secret"), ("JWT_SECRET", "short", "jwt_secret"),
    ("JWT_SECRET", "REPLACE_WITH_A_LONG_RANDOM_JWT_SECRET", "jwt_secret"),
    ("STAFF_MFA_ENCRYPTION_KEY", "not-a-fernet-key", "mfa_key"),
    ("STAFF_REQUIRE_ADMIN_MFA", "false", "staff_require_admin_mfa"),
    ("STAFF_REQUIRE_ADMIN_MFA", " true ", "staff_require_admin_mfa"),
    ("LOGIN_CODE_DEV_MODE", "true", "login_code_dev_mode"),
    ("PAYMENTS_TEST_MODE", "true", "payments_test_mode"),
    ("RERA_SAMPLE_WHEN_EMPTY", "true", "rera_sample_when_empty"),
    ("PAYMENTS_TEST_MODE", "flase", "payments_test_mode"),
    ("DATABASE_URL", "sqlite://", "database"),
    ("DATABASE_URL", "postgresql://app:change-this-local-password@db/homexo", "database"),
    ("DATABASE_URL", "postgresql://app@db/homexo?password=change_this_local_password", "database"),
    ("DATABASE_URL", "postgresql://app:@db/homexo", "database"),
    ("DATABASE_URL", "PRIVATE_INVALID_URL_CREDENTIAL", "database"),
    ("PUBLIC_SITE_URL", "http://legal.deployment.test", "public_site"),
    ("CORS_ORIGINS", "*", "cors"), ("CORS_ORIGINS", "https://other.deployment.test", "cors"),
])
def test_unsafe_settings_are_blocked(name, value, identifier):
    source = settings(); source[name] = value
    assert identifier in failures(source)


@pytest.mark.parametrize("origin", ["http://legal.test", "https://localhost", "https://127.0.0.1", "https://[::1]",
    "https://0.0.0.0", "https://user:PRIVATE@legal.test", "https://legal.test/path", "https://legal.test?q=PRIVATE",
    "https://legal.test#PRIVATE", "https://*.legal.test", "https://legal.test:bad", "https://legal.test:0", "https://[broken",
    "https://your-domain.invalid", "https://example.com", "https://legal.test\\evil", "https://legal.test\n",
    "https://127.1", "https://2130706433", "https://0x7f000001", "https://0177.0.0.1", "https://bad%20host.test",
    "https://[::ffff:127.0.0.1]", "https://[fe80::1%eth0]"])
def test_unsafe_public_origins_are_rejected(origin):
    assert https_origin(origin) is None


def test_cors_normalizes_default_ports_and_requires_all_origins_secure():
    source = settings(); source["CORS_ORIGINS"] = "https://legal.deployment.test:443/,https://staff.deployment.test:8443"
    assert not failures(source)
    source["CORS_ORIGINS"] += ",http://localhost:3000"
    assert "cors" in failures(source)


def test_dedicated_mfa_key_and_safe_non_deployment_modes():
    source = settings(); source["JWT_SECRET"] = source["STAFF_MFA_ENCRYPTION_KEY"]
    assert "mfa_key" in failures(source)
    for environment in ("development", "test", "performance"):
        assert startup_errors({"APP_ENV": environment}) == []
    assert startup_errors({"APP_ENV": "prod"}) == ["environment"]


def test_partial_providers_and_bootstrap_are_rejected():
    for changes, identifier in [
        ({"BOOTSTRAP_ADMIN_EMAIL": "admin@homexo.local", "BOOTSTRAP_ADMIN_PASSWORD": "change-this-admin-password"}, "bootstrap"),
        ({"BOOTSTRAP_ADMIN_EMAIL": "admin@firm.test"}, "bootstrap"),
        ({"BOOTSTRAP_ADMIN_EMAIL": "admin@your-domain.invalid", "BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(24)}, "bootstrap"),
        ({"S3_ACCESS_KEY_ID": "private-access-key"}, "storage_credentials"),
        ({"S3_ENDPOINT_URL": "https://objects.deployment.test"}, "storage_credentials"),
        ({"S3_BUCKET": "private-fixture", "S3_ENDPOINT_URL": "http://objects.deployment.test"}, "storage_endpoint"),
        ({"WHATSAPP_ACCESS_TOKEN": "private-token"}, "whatsapp_credentials"),
    ]:
        assert identifier in failures({**settings(), **changes})
    valid = {**settings(), "BOOTSTRAP_ADMIN_EMAIL": "admin@firm.test", "BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(24), "S3_BUCKET": "private-fixture"}
    assert not failures(valid)
    assert "bootstrap_cleanup" in {item["id"] for item in inspect_environment(valid, "production")["checks"]}


def test_payment_modes_and_incomplete_configuration():
    for target, prefix in (("staging", "rzp_test_"), ("production", "rzp_live_")):
        source = {**settings(target), "RAZORPAY_KEY_ID": prefix + "fixture", "RAZORPAY_KEY_SECRET": secrets.token_urlsafe(32), "RAZORPAY_WEBHOOK_SECRET": secrets.token_urlsafe(32)}
        assert not failures(source, target)
        source["RAZORPAY_KEY_ID"] = ("rzp_live_" if target == "staging" else "rzp_test_") + "fixture"
        assert "payments" in failures(source, target)
        source["RAZORPAY_KEY_ID"] = prefix + "fixture"; source.pop("RAZORPAY_WEBHOOK_SECRET")
        assert "payments" in failures(source, target)


def test_cli_collects_all_errors_and_never_prints_values():
    secret = "PRIVATE_CONFIGURATION_SENTINEL"
    source = {"APP_ENV": "production", "DATABASE_URL": secret, "JWT_SECRET": secret,
        "STAFF_MFA_ENCRYPTION_KEY": secret, "PUBLIC_SITE_URL": "https://user:" + secret + "@legal.test", "CORS_ORIGINS": secret}
    result = subprocess.run([sys.executable, "-m", "app.deployment_check", "--target", "production", "--json"],
        cwd=ROOT / "backend", env=source, capture_output=True, text=True, check=False)
    assert result.returncode == 1 and secret not in result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert not report["configuration_passed"] and report["failures"] >= 6
    good = subprocess.run([sys.executable, "-m", "app.deployment_check", "--target", "production"],
        cwd=ROOT / "backend", env=settings(), capture_output=True, text=True, check=False)
    assert good.returncode == 0 and "configuration" in good.stdout.lower() and "database_transport" in good.stdout


def test_config_guard_runs_before_application_or_database_imports():
    for valid in (True, False):
        source = settings()
        if not valid: source["PAYMENTS_TEST_MODE"] = "true"
        source["CORS_ORIGINS"] += ":443/"
        result = subprocess.run([sys.executable, "-c", "from app import config; import sys; assert 'app.db' not in sys.modules; assert config.CORS_ORIGINS == ['https://legal.deployment.test']"],
            cwd=ROOT / "backend", env=source, capture_output=True, text=True, check=False)
        assert result.returncode == (0 if valid else 1)
        assert source["JWT_SECRET"] not in result.stdout + result.stderr
        if not valid: assert "payments_test_mode" in result.stderr


def test_checked_in_templates_fail_until_real_configuration_is_supplied():
    for target in ("staging", "production"):
        path = ROOT / "infra/environments" / (target + ".env.example")
        source = dict(line.split("=", 1) for line in path.read_text().splitlines() if line and not line.startswith("#"))
        assert source["APP_ENV"] == target
        assert {"jwt_secret", "mfa_key", "database", "public_site", "cors"} <= failures(source, target)
        assert not {"login_code_dev_mode", "payments_test_mode", "rera_sample_when_empty", "staff_require_admin_mfa"} & failures(source, target)
