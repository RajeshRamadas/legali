"""Bounded, read-only loopback load checks. Reports contain aggregates, never bodies/tokens."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]
MAX_RESPONSE_BYTES = 1024 * 1024


def validate(profile, base_url):
    url = urlsplit(base_url)
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError('Invalid performance API port.')
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost', '::1') or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        raise ValueError('Performance checks require an HTTP loopback origin without credentials or a path.')
    limits = {'concurrency': (1, 32), 'requests': (10, 1000), 'warmup': (0, 10), 'rate_per_second': (1, 200), 'timeout_seconds': (1, 10), 'max_seconds': (1, 300), 'p95_ms': (1, 30000), 'max_error_rate': (0, .1)}
    if not isinstance(profile, dict) or set(profile) != set(limits) | {'scenarios'}:
        raise ValueError('Performance profile has missing or unknown fields.')
    for name, (low, high) in limits.items():
        value = profile[name]
        integer = name in ('concurrency', 'requests', 'warmup', 'max_seconds')
        if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Performance profile contains an invalid bounded setting.')
    scenarios = profile['scenarios']
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 12 or len(scenarios) * (profile['requests'] + profile['warmup']) > 5000:
        raise ValueError('Performance profile exceeds the scenario/request bounds.')
    names = set()
    for item in scenarios:
        if not isinstance(item, dict) or set(item) != {'name', 'path', 'auth', 'expect'}:
            raise ValueError('Scenario fields are missing or unknown.')
        if not isinstance(item['name'], str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', item['name']) or item['name'] in names:
            raise ValueError('Scenario names must be unique bounded labels.')
        names.add(item['name'])
        path = item['path']
        if not isinstance(path, str) or len(path) > 250 or not re.fullmatch(r'/[A-Za-z0-9/_?=&.-]*', path) or path.startswith('//') or '..' in path or urlsplit(path).scheme or urlsplit(path).netloc:
            raise ValueError('Scenario paths must be bounded relative API paths.')
        if item['auth'] not in ('public', 'customer', 'admin') or not isinstance(item['expect'], dict) or not item['expect']:
            raise ValueError('A scenario needs a known identity and response contract.')
        for key, value in item['expect'].items():
            if not isinstance(key, str) or not re.fullmatch(r'[a-z_]{1,40}', key) or not isinstance(value, str) or value not in ('ok', 'ready', 'nonempty_list'):
                raise ValueError('Unknown response contract.')
    return profile


def percentile(values, fraction):
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 2) if values else None


def matches(body, contract):
    return isinstance(body, dict) and all((isinstance(body.get(key), list) and bool(body[key])) if value == 'nonempty_list' else body.get(key) == value for key, value in contract.items())


async def sample(client, scenario, headers):
    started = time.perf_counter()
    status, error = None, None
    try:
        async with client.stream('GET', scenario['path'], headers=headers) as response:
            status = response.status_code
            if status != 200:
                error = 'rate_limited' if status == 429 else 'http_status'
            else:
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                        error = 'response_too_large'
                        break
                    data.extend(chunk)
                if error is None:
                    try:
                        error = None if matches(json.loads(data), scenario['expect']) else 'response_contract'
                    except (ValueError, UnicodeError):
                        error = 'invalid_json'
    except httpx.TimeoutException:
        error = 'timeout'
    except httpx.HTTPError:
        error = 'transport'
    return {'ms': (time.perf_counter() - started) * 1000, 'status': status, 'error': error}


async def scenario_run(client, scenario, profile, token):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    warmup = [await sample(client, scenario, headers) for _ in range(profile['warmup'])]
    semaphore = asyncio.Semaphore(profile['concurrency'])
    started = time.perf_counter()
    async def request(index):
        due = started + index / profile['rate_per_second']
        await asyncio.sleep(max(0, due - time.perf_counter()))
        async with semaphore:
            lag = max(0, time.perf_counter() - due) * 1000
            result = await sample(client, scenario, headers)
            result['lag_ms'] = lag
            return result
    values = await asyncio.gather(*(request(index) for index in range(profile['requests'])))
    elapsed = time.perf_counter() - started
    errors = Counter(row['error'] for row in values if row['error'])
    latencies = [row['ms'] for row in values]
    warmup_errors = sum(bool(row['error']) for row in warmup)
    p95 = percentile(latencies, .95)
    error_rate = sum(errors.values()) / len(values)
    return {'name': scenario['name'], 'passed': warmup_errors == 0 and error_rate <= profile['max_error_rate'] and p95 <= profile['p95_ms'],
        'requests': len(values), 'warmup_errors': warmup_errors, 'errors': dict(errors), 'error_rate': error_rate,
        'statuses': dict(Counter(str(row['status']) for row in values if row['status'] is not None)),
        'p50_ms': percentile(latencies, .5), 'p95_ms': p95, 'p99_ms': percentile(latencies, .99),
        'dispatch_lag_p95_ms': percentile([row['lag_ms'] for row in values], .95), 'throughput_rps': round(len(values) / elapsed, 2)}


async def execute(profile, base_url, tokens, *, transport=None):
    validate(profile, base_url)
    for item in profile['scenarios']:
        if item['auth'] != 'public' and not tokens.get(item['auth']):
            raise ValueError('A required performance identity is missing.')
    report = {'version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(), 'complete': False, 'passed': False,
        'settings': {key: value for key, value in profile.items() if key != 'scenarios'}, 'scenarios': [], 'errors': []}
    try:
        async with asyncio.timeout(profile['max_seconds']):
            async with httpx.AsyncClient(base_url=base_url.rstrip('/'), timeout=profile['timeout_seconds'], follow_redirects=False,
                trust_env=False, transport=transport, limits=httpx.Limits(max_connections=profile['concurrency'], max_keepalive_connections=profile['concurrency'])) as client:
                for item in profile['scenarios']:
                    report['scenarios'].append(await scenario_run(client, item, profile, tokens.get(item['auth'])))
            report['complete'] = True
    except TimeoutError:
        report['errors'].append('run_deadline')
    except (httpx.HTTPError, OSError):
        report['errors'].append('driver_failure')
    report['passed'] = report['complete'] and not report['errors'] and all(item['passed'] for item in report['scenarios'])
    return report


def write_report(report, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# API performance results', '', f"Result: {'PASS' if report['passed'] else 'FAIL'}", '', '| Scenario | Requests | p95 ms | Errors | Warm-up errors | Result |', '| --- | ---: | ---: | ---: | ---: | --- |']
    for item in report['scenarios']:
        lines.append(f"| {item['name']} | {item['requests']} | {item['p95_ms']} | {sum(item['errors'].values())} | {item['warmup_errors']} | {'PASS' if item['passed'] else 'FAIL'} |")
    if report['errors']: lines += ['', 'Driver failure: ' + ', '.join(report['errors'])]
    destination.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(f"Performance result: {'PASS' if report['passed'] else 'FAIL'}; {len(report['scenarios'])} completed scenarios")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8766')
    parser.add_argument('--profile', type=Path, default=ROOT / 'ci/performance.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'performance-reports/results.json')
    args = parser.parse_args()
    # Remove stale successes before any validation/network work.
    args.output.unlink(missing_ok=True); args.output.with_suffix('.md').unlink(missing_ok=True)
    try:
        profile = json.loads(args.profile.read_text())
        report = asyncio.run(execute(profile, args.base_url, {'customer': os.getenv('PERF_CUSTOMER_TOKEN'), 'admin': os.getenv('PERF_ADMIN_TOKEN')}))
        write_report(report, args.output)
        return 0 if report['passed'] else 1
    except Exception:
        print('Performance configuration or driver failed; no successful report was produced.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
