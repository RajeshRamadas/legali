import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.performance import run, seed
from scripts.performance.check import isolated_environment
from app.db import SessionLocal
from app.models import Base, CustomerAccount


def profile(**changes):
    result = json.loads((ROOT / 'ci/performance.json').read_text())
    result.update({'requests': 10, 'warmup': 0, 'rate_per_second': 200, 'scenarios': [result['scenarios'][0]], **changes})
    return result


def execute(handler, value=None, tokens=None):
    return asyncio.run(run.execute(value or profile(), 'http://127.0.0.1:8766', tokens or {}, transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize('url', ['https://example.com', 'http://example.com', 'http://127.0.0.1/path', 'http://user:secret@127.0.0.1', 'http://127.0.0.1?token=secret', 'file:///tmp/test', 'http://127.0.0.1:99999'])
def test_non_loopback_or_credentialed_origins_fail(url):
    with pytest.raises(ValueError): run.validate(profile(), url)


@pytest.mark.parametrize('changes', [{'concurrency': True}, {'requests': 0}, {'concurrency': 33}, {'rate_per_second': float('nan')}, {'max_seconds': 301}, {'max_error_rate': .5}, {'p95_ms': 0}, {'unknown': 1}])
def test_unbounded_and_invalid_profiles_fail(changes):
    with pytest.raises(ValueError): run.validate(profile(**changes), 'http://127.0.0.1:8766')


@pytest.mark.parametrize('path', ['https://example.com/private', '//example.com/private', '/api/../private', '/api#secret', '/api\\private'])
def test_paths_cannot_change_origin_or_escape_route(path):
    value = profile(); value['scenarios'][0]['path'] = path
    with pytest.raises(ValueError): run.validate(value, 'http://127.0.0.1:8766')


def test_success_is_based_on_real_contracts_and_has_no_credentials(tmp_path):
    value = profile(); value['scenarios'][0]['auth'] = 'customer'
    seen = []
    def handle(request):
        seen.append(request.headers.get('Authorization'))
        return httpx.Response(200, json={'status': 'ok', 'private_data': 'PRIVATE_RESPONSE_MARKER'})
    report = execute(handle, value, {'customer': 'PRIVATE_TOKEN_MARKER'})
    assert report['passed'] and report['complete'] and report['scenarios'][0]['requests'] == 10
    assert seen == ['Bearer PRIVATE_TOKEN_MARKER'] * 10
    destination = tmp_path / 'results.json'; run.write_report(report, destination)
    content = destination.read_text() + destination.with_suffix('.md').read_text()
    assert 'PRIVATE_TOKEN_MARKER' not in content and 'PRIVATE_RESPONSE_MARKER' not in content and '/health' not in content


@pytest.mark.parametrize('status,body,category', [(401, {}, 'http_status'), (429, {}, 'rate_limited'), (503, {}, 'http_status'), (200, {'status':'wrong'}, 'response_contract'), (302, {}, 'http_status')])
def test_http_failures_and_empty_or_wrong_contracts_fail(status, body, category):
    report = execute(lambda request: httpx.Response(status, json=body))
    assert not report['passed'] and report['scenarios'][0]['errors'][category] == 10


def test_html_and_oversized_bodies_do_not_pass():
    for data, error in ((b'<html>Login form</html>', 'invalid_json'), (b'x' * (run.MAX_RESPONSE_BYTES + 1), 'response_too_large')):
        report = execute(lambda request: httpx.Response(200, content=data))
        assert not report['passed'] and report['scenarios'][0]['errors'][error] == 10


def test_timeout_and_transport_messages_are_redacted():
    for exception, error in ((httpx.ReadTimeout('PRIVATE_TOKEN_MARKER'), 'timeout'), (httpx.ConnectError('PRIVATE_DATABASE_URL'), 'transport')):
        def handle(request): raise exception
        report = execute(handle)
        assert not report['passed'] and report['scenarios'][0]['errors'][error] == 10
        assert 'PRIVATE_' not in json.dumps(report)


def test_warmup_errors_cannot_be_hidden_by_fast_successes():
    calls = 0
    def handle(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={}) if calls == 1 else httpx.Response(200, json={'status':'ok'})
    report = execute(handle, profile(warmup=1))
    assert not report['passed'] and report['scenarios'][0]['warmup_errors'] == 1 and report['scenarios'][0]['errors'] == {}


def test_latency_budget_and_global_deadline_fail():
    async def slow(request):
        await asyncio.sleep(.02)
        return httpx.Response(200, json={'status':'ok'})
    assert not execute(slow, profile(p95_ms=1))['passed']
    report = execute(lambda request: httpx.Response(200, json={'status':'ok'}), profile(requests=10, rate_per_second=1, max_seconds=1))
    assert not report['complete'] and not report['passed'] and report['errors'] == ['run_deadline']


def test_missing_identity_is_rejected_before_requests():
    value = profile(); value['scenarios'][0]['auth'] = 'admin'
    with pytest.raises(ValueError): execute(lambda request: pytest.fail('No request should be sent'), value)


def test_environment_isolates_workers_providers_and_refuses_application_database(tmp_path):
    source = {'APP_ENV':'performance','DATABASE_URL':'postgresql+psycopg://user:secret@localhost/legali_perf_test','WHATSAPP_ACCESS_TOKEN':'PRIVATE_PROVIDER_KEY', 'S3_SECRET_ACCESS_KEY':'PRIVATE_STORAGE_KEY', 'RAZORPAY_WEBHOOK_SECRET':'PRIVATE_WEBHOOK_KEY'}
    env = isolated_environment(source, tmp_path)
    assert all(env[name] == 'false' for name in seed.WORKERS)
    assert all(not env[name] for name in seed.PROVIDERS)
    assert env['STAFF_REQUIRE_ADMIN_MFA'] == 'true' and len(env['JWT_SECRET']) >= 32
    assert source['WHATSAPP_ACCESS_TOKEN'] == 'PRIVATE_PROVIDER_KEY'
    for changes in ({'APP_ENV':'production'}, {'DATABASE_URL':'postgresql+psycopg://user:secret@localhost/homexo'}, {'DATABASE_URL':'sqlite://'}):
        with pytest.raises(ValueError): isolated_environment({**source, **changes}, tmp_path)
    with pytest.raises(ValueError): seed.validate_environment({**env,'NOTIFY_WORKER_ENABLED':'true'})
    with pytest.raises(ValueError): seed.validate_environment({**env,'RAZORPAY_KEY_ID':'provider-key'})


def test_seed_refuses_existing_business_rows():
    with SessionLocal() as db:
        seed.ensure_empty(db, Base.metadata.sorted_tables)
        db.add(CustomerAccount(phone_normalized='0000000000')); db.commit()
        with pytest.raises(ValueError): seed.ensure_empty(db, Base.metadata.sorted_tables)


def test_percentiles_use_nearest_rank_and_no_empty_success():
    assert run.percentile(list(range(1,101)), .95) == 95
    assert run.percentile([], .95) is None
    value = profile(); value['scenarios'] = []
    with pytest.raises(ValueError): run.validate(value, 'http://127.0.0.1:8766')
    duplicate = profile(); duplicate['scenarios'] *= 2
    with pytest.raises(ValueError): run.validate(duplicate, 'http://127.0.0.1:8766')
