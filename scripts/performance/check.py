"""Migrate and seed a reserved test database, run a temporary API, and retain sanitized results."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from cryptography.fernet import Fernet
import httpx

from .seed import PROVIDERS, WORKERS, validate_environment, assert_target_empty
from .run import ROOT, execute, validate, write_report


def isolated_environment(source, storage):
    # Check the caller's explicit target before migrations or any process starts.
    env = dict(source)
    env.update(APP_ENV='performance', JWT_SECRET=secrets.token_urlsafe(48), STAFF_MFA_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        STAFF_REQUIRE_ADMIN_MFA='true', LOCAL_STORAGE_DIR=str(storage), AWS_EC2_METADATA_DISABLED='true',
        API_LOOKUPS_PER_MINUTE='100000', API_WRITES_PER_MINUTE='100000', VERIFICATION_UPLOAD_CHECKS='false', PAYMENTS_TEST_MODE='false')
    if source.get('APP_ENV') != 'performance':
        raise ValueError('Explicitly select APP_ENV=performance before running this command.')
    for name in PROVIDERS: env[name] = ''
    for name in WORKERS: env[name] = 'false'
    validate_environment(env)
    return env


def run_check(profile_path, output, port):
    output.unlink(missing_ok=True); output.with_suffix('.md').unlink(missing_ok=True)
    if not 1024 <= port <= 65535:
        raise ValueError('Use an unprivileged loopback port.')
    profile = json.loads(profile_path.read_text()); base_url = f'http://127.0.0.1:{port}'
    validate(profile, base_url)
    with tempfile.TemporaryDirectory(prefix='legali-performance-') as temporary:
        directory = Path(temporary)
        env = isolated_environment(os.environ, directory / 'storage')
        assert_target_empty(env['DATABASE_URL'])
        # Refuse occupied ports rather than accidentally benchmarking another process.
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise ValueError('The performance API port is already in use.')
        with (directory / 'process.log').open('wb') as log:
            print('Performance stage: migrations', flush=True)
            subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT / 'backend', env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
            identity_path = directory / 'identity.json'
            print('Performance stage: synthetic fixtures', flush=True)
            subprocess.run([sys.executable, str(ROOT / 'scripts/performance/seed.py'), '--output', str(identity_path)], cwd=ROOT, env=env,
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
            identity = json.loads(identity_path.read_text())
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
                cwd=ROOT / 'backend', env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                ready = False
                with httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as client:
                    deadline = time.monotonic() + 30
                    while process.poll() is None and time.monotonic() < deadline:
                        try:
                            response = client.get(base_url + '/ready')
                            if response.status_code == 200 and response.json() == {'status': 'ready'}:
                                ready = True; break
                        except (httpx.HTTPError, ValueError):
                            pass
                        time.sleep(.2)
                if not ready: raise ValueError('Temporary performance API failed readiness.')
                print('Performance stage: load checks', flush=True)
                report = asyncio.run(execute(profile, base_url, identity))
                report['fixture'] = identity['counts']
                report['environment'] = {'database': 'PostgreSQL', 'workers': 'disabled', 'api_budget': 'raised_for_isolated_load', 'authentication': 'normal_verified_fixture_sessions'}
                write_report(report, output)
                return 0 if report['passed'] else 1
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=ROOT / 'ci/performance.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'performance-reports/results.json')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    try:
        sys.exit(run_check(args.profile, args.output, args.port))
    except Exception:
        write_report({'version': 1, 'complete': False, 'passed': False, 'settings': {}, 'scenarios': [], 'errors': ['setup_or_driver_failed']}, args.output)
        print('Performance check failed before a complete report. Verify the reserved empty database and local runtime; credentials/process logs are not published.', file=sys.stderr)
        sys.exit(1)
