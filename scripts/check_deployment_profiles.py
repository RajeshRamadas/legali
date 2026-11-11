"""Render example Compose profiles with temporary secrets; validate actual API environment wiring."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.deployment import inspect_environment  # noqa: E402


def main():
    # Config rendering is offline: no daemon, image build, containers or configured .env are used.
    env = {name: value for name, value in os.environ.items() if name in (
        "PATH", "HOME", "DOCKER_CONFIG", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
        "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "LANG", "LC_ALL")}
    for target in ("staging", "production"):
        settings = {"DATABASE_URL": "postgresql+psycopg://fixture:" + secrets.token_urlsafe(24) + "@db/deployment_fixture",
            "JWT_SECRET": secrets.token_urlsafe(48), "STAFF_MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "PUBLIC_SITE_URL": "https://legal.deployment.test", "CORS_ORIGINS": "https://LEGAL.deployment.test:443/",
            "VERIFICATION_PROCESSOR_NAME": "Synthetic verification processor",
            "VERIFICATION_PROCESSOR_PRIVACY_URL": "https://privacy.deployment.test/policy"}
        with tempfile.TemporaryDirectory(prefix="legali-profile-check-") as directory:
            override = Path(directory) / "private.env"
            descriptor = os.open(override, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write("\n".join(f"{name}={value}" for name, value in settings.items()) + "\n")
            command = ["docker", "--host=unix:///var/run/docker.sock", "compose", "-f", "infra/docker-compose.yml",
                "--env-file", f"infra/environments/{target}.env.example", "--env-file", str(override), "--profile", "verification", "config", "--format", "json"]
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=True, timeout=30)
            services = json.loads(result.stdout)["services"]
            api = services["api"]["environment"]
            worker = services["verification-worker"]["environment"]
            for setting in ("VERIFICATION_PROCESSOR_NAME", "VERIFICATION_PROCESSOR_PRIVACY_URL"):
                if api.get(setting) != settings[setting] or worker.get(setting) != settings[setting]:
                    raise ValueError("Processor disclosure settings were not forwarded consistently to API and verification worker.")
            report = inspect_environment(api, target)
            if (not report["configuration_passed"] or api["APP_ENV"] != target
                or api["BOOTSTRAP_ADMIN_EMAIL"] or api["BOOTSTRAP_ADMIN_PASSWORD"]
                or api["NOTIFY_WORKER_ENABLED"] != "false"
                or api.get("SUPPORT_DEADLINE_EMAIL_ENABLED") != "false"
                or api.get("SUPPORT_REPLY_NOTIFICATIONS_ENABLED") != "false"):
                raise ValueError("Deployment profile did not preserve its explicit settings.")
            settings.update(SUPPORT_DEADLINE_EMAIL_ENABLED="true", SUPPORT_REPLY_NOTIFICATIONS_ENABLED="true", SUPPORT_ESCALATION_HOURS="36")
            override.write_text("\n".join(f"{name}={value}" for name, value in settings.items()) + "\n")
            configured = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=True, timeout=30)
            wired = json.loads(configured.stdout)["services"]["api"]["environment"]
            if (wired.get("SUPPORT_DEADLINE_EMAIL_ENABLED") != "true" or wired.get("SUPPORT_REPLY_NOTIFICATIONS_ENABLED") != "true"
                or wired.get("SUPPORT_ESCALATION_HOURS") != "36" or wired["NOTIFY_WORKER_ENABLED"] != "false"):
                raise ValueError("Support delivery settings were not forwarded to the API environment.")
            print(f"{target}: rendered configuration passed; bootstrap/shortcuts disabled; support delivery opt-ins verified.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("Deployment profile validation failed. Check Compose availability and the example/profile wiring; values are withheld.", file=sys.stderr)
        raise SystemExit(1)
