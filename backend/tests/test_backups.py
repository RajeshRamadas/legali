"""Recovery safety tests; real PostgreSQL/GnuPG drill is infra/backup/test_recovery.py."""
import hashlib
import importlib.util
import io
import json
import os
import signal
import subprocess
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("homexo_backup", ROOT / "infra/backup/backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_postgres_url_keeps_credentials_out_of_arguments_and_honors_tls():
    env = backup.postgres_env("postgresql+psycopg://backup_user:one%40two%3Athree@db:5433/homexo?sslmode=verify-full&sslrootcert=%2Fsecure%2Fca.pem")
    assert env["PGPASSWORD"] == "one@two:three"
    assert env["PGDATABASE"] == "homexo" and env["PGHOST"] == "db" and env["PGPORT"] == "5433"
    assert env["PGSSLMODE"] == "verify-full" and env["PGSSLROOTCERT"] == "/secure/ca.pem"


@pytest.mark.parametrize("url", ["", "sqlite:///test", "postgresql:///homexo", "postgresql://db/", "postgresql://db/dbname=x", "postgresql://db/homexo?options=bad", "postgresql://db:bad/homexo"])
def test_unsupported_connections_fail_without_echoing_secrets(url):
    with pytest.raises(backup.BackupError) as error:
        backup.postgres_env(url)
    assert "postgresql://" not in str(error.value)


@pytest.mark.parametrize("key", ["../escape", "/absolute", "nested/../escape", "nested//file", "a/./file", "a\\file", "", "bad\nname"])
def test_archive_path_traversal_is_rejected(key):
    with pytest.raises(backup.BackupError):
        backup.safe_key(key)


def archive(tmp_path, *, entries=None, change=None, extra=None):
    entries = entries or {"database.dump": b"fake PostgreSQL custom dump", "documents/tickets/HX-TEST/file.pdf": b"synthetic PDF"}
    manifest = {"format": backup.FORMAT, "schema_revisions": ["0021_api_abuse_protection"], "storage_backend": "local", "files": [
        {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for path, data in entries.items()]}
    if change:
        change(manifest)
    path = tmp_path / "backup.tar"
    with tarfile.open(path, "w") as tar:
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
        data = json.dumps(manifest).encode()
        member = tarfile.TarInfo("manifest.json")
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
        if extra:
            tar.addfile(extra, io.BytesIO(b""))
    staging = tmp_path / "unpacked"
    staging.mkdir(mode=0o700)
    return path, staging


def test_archive_verification_preserves_paths_and_checksums(tmp_path):
    path, staging = archive(tmp_path)
    manifest = backup.unpack(path, staging, 1024)
    assert len(manifest["files"]) == 2
    assert (staging / "documents/tickets/HX-TEST/file.pdf").read_bytes() == b"synthetic PDF"
    assert (staging / "database.dump").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("change", [
    lambda m: m.update(format="unknown"),
    lambda m: m.pop("schema_revisions"),
    lambda m: m.update(storage_backend="unknown"),
    lambda m: m["files"][0].update(sha256="0" * 64),
    lambda m: m["files"][0].update(size=999),
    lambda m: m["files"].pop(),
    lambda m: m["files"].append(m["files"][0]),
])
def test_corrupt_inventories_are_rejected_before_restore(tmp_path, change):
    path, staging = archive(tmp_path, change=change)
    with pytest.raises(backup.BackupError):
        backup.unpack(path, staging, 1024)


@pytest.mark.parametrize("name,kind", [("../outside", tarfile.REGTYPE), ("documents/link", tarfile.SYMTYPE), ("documents/hardlink", tarfile.LNKTYPE), ("database.dump", tarfile.REGTYPE), ("other", tarfile.REGTYPE)])
def test_unsafe_tar_members_never_extract(tmp_path, name, kind):
    extra = tarfile.TarInfo(name)
    extra.type = kind
    extra.linkname = "/etc/passwd"
    path, staging = archive(tmp_path, extra=extra)
    with pytest.raises(backup.BackupError):
        backup.unpack(path, staging, 1024)
    assert not list(staging.iterdir())
    assert not (tmp_path / "outside").exists()


def test_archive_expansion_is_bounded(tmp_path):
    path, staging = archive(tmp_path)
    with pytest.raises(backup.BackupError):
        backup.unpack(path, staging, 1)
    assert not list(staging.iterdir())


def test_missing_and_changed_database_references_abort_backup():
    record = {"path": "documents/file.pdf", "size": 3, "sha256": "a" * 64}
    expected = {"key": "file.pdf", "size": 3, "sha256": "a" * 64}
    backup.check_document_inventory([record], [expected])
    for changes in ({"key": "missing.pdf"}, {"size": 4}, {"sha256": "b" * 64}):
        with pytest.raises(backup.BackupError):
            backup.check_document_inventory([record], [{**expected, **changes}])


def test_source_storage_links_and_special_files_fail_closed(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    (root / "linked-directory").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(backup.BackupError):
        list(backup.local_documents(root))
    (root / "linked-directory").unlink()
    os.mkfifo(root / "pipe")
    with pytest.raises(backup.BackupError):
        list(backup.local_documents(root))


def test_s3_backup_reads_only_configured_prefix_and_keeps_relative_storage_keys(tmp_path, monkeypatch):
    import boto3
    from moto import mock_aws
    # Moto uses synthetic credentials and intercepts all S3 requests.
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="synthetic-backup-source")
        client.put_object(Bucket="synthetic-backup-source", Key="homexo/tickets/HX-TEST/file.pdf", Body=b"synthetic")
        client.put_object(Bucket="synthetic-backup-source", Key="homexo/tickets/", Body=b"")
        client.put_object(Bucket="synthetic-backup-source", Key="unrelated/private", Body=b"excluded")
        monkeypatch.setenv("S3_BUCKET", "synthetic-backup-source")
        monkeypatch.setenv("S3_REGION", "us-east-1")
        monkeypatch.setenv("S3_KEY_PREFIX", "homexo/")
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
        contents = [(key, path.read_bytes()) for key, path in backup.s3_documents(tmp_path)]
        assert contents == [("tickets/HX-TEST/file.pdf", b"synthetic")]
        assert not list(tmp_path.iterdir())
        assert client.get_object(Bucket="synthetic-backup-source", Key="unrelated/private")["Body"].read() == b"excluded"


def test_retention_is_dry_run_by_default_and_always_keeps_latest(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir(mode=0o700)
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    names = ["homexo-backup-20260101T000000Z-00000001.tar.gpg", "homexo-backup-20260201T000000Z-00000002.tar.gpg"]
    for name in names + ["unrelated.gpg", "homexo-backup-20260101T000000Z-00000003.tar.gpg.partial"]:
        (directory / name).write_bytes(b"encrypted")
    link = directory / "homexo-backup-20260101T000000Z-00000004.tar.gpg"
    link.symlink_to(directory / names[1])
    (directory / "homexo-backup-20269999T000000Z-00000005.tar.gpg").write_bytes(b"ignore malformed date")
    result = backup.prune(directory, 30, now=now)
    assert result["dry_run"] and result["expired"] == [names[0]]
    assert (directory / names[0]).exists()
    backup.prune(directory, 30, apply=True, now=now)
    assert not (directory / names[0]).exists()
    assert (directory / names[1]).exists() and link.is_symlink()
    assert (directory / "unrelated.gpg").exists()


def test_freshness_rejects_missing_stale_future_and_partial_backups(tmp_path):
    tmp_path.chmod(0o700)
    now = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    with pytest.raises(backup.BackupError):
        backup.status(tmp_path, 26, now=now)
    path = tmp_path / "homexo-backup-20261108T120000Z-00000001.tar.gpg"
    path.write_bytes(b"encrypted")
    assert backup.status(tmp_path, 26, now=now)["age_hours"] == 24
    with pytest.raises(backup.BackupError):
        backup.status(tmp_path, 23, now=now)
    with pytest.raises(backup.BackupError):
        backup.status(tmp_path, 26, now=now - timedelta(days=2))


def test_backup_and_restore_require_writers_stopped_before_any_work(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Unsafe operation reached a subprocess")
    monkeypatch.setattr(backup, "run", unexpected)
    with pytest.raises(backup.BackupError, match="writers"):
        backup.create(tmp_path)
    with pytest.raises(backup.BackupError, match="writers"):
        backup.restore("missing", tmp_path)


def test_backup_directory_rejects_insecure_permissions_and_overlapping_jobs(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    with pytest.raises(backup.BackupError):
        backup.private_dir(directory)
    directory.chmod(0o700)
    with backup.directory_lock(directory):
        with pytest.raises(backup.BackupError):
            with backup.directory_lock(directory):
                pass


@pytest.mark.parametrize("case", ["success", "backup_failure", "already_stopped", "restart_failure", "interrupted", "writer_check_failure"])
def test_scheduler_restarts_api_after_backup_success_or_failure(tmp_path, case):
    binary = tmp_path / "docker"
    log = tmp_path / "commands.jsonl"
    binary.write_text('''#!/usr/bin/env python3
import json, os, sys, time
args=sys.argv[1:]
with open(os.environ['SCHEDULE_TEST_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')
case=os.environ['SCHEDULE_TEST_CASE']
if 'ps' in args and '--services' in args:
 print('db' if case=='already_stopped' else 'api\\ndb')
if 'ps' in args and '-q' in args and 'api' in args and case=='writer_check_failure': sys.exit(9)
if 'ps' in args and '--filter' in args and case in ('backup_failure','interrupted'): print('synthetic-owned-job')
if 'run' in args and case=='backup_failure': sys.exit(7)
if 'run' in args and case=='interrupted':
 open(os.environ['SCHEDULE_TEST_READY'],'w').close()
 time.sleep(30)
if 'start' in args and case=='restart_failure': sys.exit(8)
''')
    binary.chmod(0o700)
    ready = tmp_path / "running"
    env = {**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "SCHEDULE_TEST_LOG": str(log), "SCHEDULE_TEST_CASE": case, "SCHEDULE_TEST_READY": str(ready)}
    command = ["bash", str(ROOT / "infra/backup/run-scheduled.sh")]
    if case == "interrupted":
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(0.02)
            assert ready.exists()
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=5)
            result = process
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    else:
        result = subprocess.run(command, env=env, capture_output=True)
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    assert (result.returncode == 0) == (case == "success")
    assert any("start" in command for command in commands) == (case != "already_stopped")
    assert any("run" in command for command in commands) == (case not in ("already_stopped", "writer_check_failure"))
    if case in ("backup_failure", "interrupted"):
        stopped_job = next(i for i, command in enumerate(commands) if command[:2] == ["stop", "--time"])
        restarted_api = next(i for i, command in enumerate(commands) if "start" in command)
        assert stopped_job < restarted_api
