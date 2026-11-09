#!/usr/bin/env python3
"""Offline recovery tooling. PostgreSQL clients and GnuPG must be on PATH."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, unquote, urlsplit

FORMAT = "homexo-backup-v1"
BACKUP_NAME = re.compile(r"homexo-backup-(\d{8}T\d{6}Z)-[a-f0-9]{8}\.tar\.gpg\Z")
CHUNK = 1024 * 1024


class BackupError(Exception):
    pass


def run(command, *, env=None, output=False):
    try:
        result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if output else subprocess.DEVNULL, stderr=subprocess.PIPE)
    except OSError:
        raise BackupError(f"Cannot run {Path(command[0]).name}; install the required tool and check permissions.") from None
    if result.returncode:
        # Provider/SQL errors may contain customer information. Keep diagnostics out of job logs.
        raise BackupError(f"{Path(command[0]).name} failed (exit {result.returncode}); check credentials, connectivity, disk space and tool versions.")
    return result.stdout.decode().strip() if output else None


def postgres_env(url):
    try:
        parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
        database = unquote(parsed.path.lstrip("/"))
        if parsed.scheme not in ("postgresql", "postgres") or not parsed.hostname or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", database):
            raise ValueError
        env = os.environ.copy()
        env.update(PGHOST=parsed.hostname, PGPORT=str(parsed.port or 5432), PGDATABASE=database,
            PGCONNECT_TIMEOUT="15", PGAPPNAME="homexo-backup")
        if parsed.username is not None:
            env["PGUSER"] = unquote(parsed.username)
        if parsed.password is not None:
            env["PGPASSWORD"] = unquote(parsed.password)
        options = {"sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT", "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY", "connect_timeout": "PGCONNECT_TIMEOUT"}
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key not in options:
                raise ValueError
            env[options[key]] = value
        return env
    except (ValueError, TypeError):
        raise BackupError("Provide a PostgreSQL URL with a host and database name; only SSL and connection-timeout query options are supported.") from None


def query(env, sql):
    return run(["psql", "-X", "--no-password", "--set=ON_ERROR_STOP=1", "--tuples-only", "--no-align", "--command", sql], env=env, output=True)


def private_dir(path):
    path = Path(path).absolute()
    if path.is_symlink():
        raise BackupError("Backup directories must not be symbolic links.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir() or path.stat().st_mode & 0o077:
        raise BackupError("Backup directories must be private; use chmod 700 on the directory.")
    return path


@contextlib.contextmanager
def directory_lock(directory):
    fd = os.open(directory / ".backup.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError("Another backup or retention job is running.") from None
        yield
    finally:
        os.close(fd)


def safe_key(value):
    if not value or "\\" in value or any(ord(char) < 32 for char in value):
        raise BackupError("Unsafe document or archive path.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise BackupError("Unsafe document or archive path.")
    return value


def digest(path):
    hashed = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            hashed.update(block)
    return hashed.hexdigest()


def check_document_inventory(records, expected):
    inventory = {item["path"]: item for item in records}
    for document in expected:
        key = "documents/" + safe_key(document["key"])
        item = inventory.get(key)
        if item is None or item["size"] != document["size"] or (document["sha256"] and item["sha256"] != document["sha256"]):
            raise BackupError("A referenced document is missing or changed; no completed backup was published.")


def local_documents(root):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise BackupError("The local document directory must exist and must not be a symbolic link.")
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink() or (name in files and not path.is_file()):
                raise BackupError("Document storage contains a link or special file; backup stopped.")
        for name in sorted(files):
            path = Path(directory) / name
            yield safe_key(path.relative_to(root).as_posix()), path


def s3_documents(staging):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise BackupError("S3 backups require boto3 (included in the backup image).") from None
    prefix = os.getenv("S3_KEY_PREFIX", "homexo/").lstrip("/")
    client = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        region_name=os.getenv("S3_REGION") or None,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY") or None,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}))
    try:
        pages = client.get_paginator("list_objects_v2").paginate(Bucket=os.environ["S3_BUCKET"], Prefix=prefix)
        for page in pages:
            for item in page.get("Contents", []):
                key = item["Key"]
                relative = key[len(prefix):]
                if key.endswith("/") and item["Size"] == 0:
                    continue
                relative = safe_key(relative)
                # Use opaque temporary names: object keys never become staging paths.
                target = staging / uuid.uuid4().hex
                response = client.get_object(Bucket=os.environ["S3_BUCKET"], Key=key, IfMatch=item["ETag"])
                try:
                    with target.open("xb") as out:
                        shutil.copyfileobj(response["Body"], out, CHUNK)
                finally:
                    response["Body"].close()
                yield relative, target
                target.unlink()
    except BackupError:
        raise
    except Exception:
        raise BackupError("Cannot read the complete S3 document prefix; check access and keep writers stopped.") from None
    finally:
        client.close()


@contextlib.contextmanager
def workspace():
    parent = os.getenv("BACKUP_WORK_DIR") or None
    if parent:
        parent = private_dir(parent)
    with tempfile.TemporaryDirectory(prefix="homexo-recovery-", dir=parent) as name:
        work = Path(name)
        home = work / "gnupg"
        home.mkdir(mode=0o700)
        try:
            yield work, ["gpg", "--no-options", "--homedir", str(home), "--batch", "--no-tty", "--pinentry-mode", "loopback"]
        finally:
            # Secret-key imports start a private agent. Do not leave it or its sockets behind.
            subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def create(output_dir, *, writers_stopped=False):
    if not writers_stopped:
        raise BackupError("Stop all API/worker writers, then pass --writers-stopped for a consistent database/document snapshot.")
    env = postgres_env(os.getenv("DATABASE_URL", ""))
    public_key = Path(os.environ.get("BACKUP_PUBLIC_KEY_FILE", "")).absolute()
    if not public_key.is_file():
        raise BackupError("Set BACKUP_PUBLIC_KEY_FILE to the recovery public key file.")
    output_dir = private_dir(output_dir)
    source = Path(os.getenv("LOCAL_STORAGE_DIR", "backend/storage")).resolve()
    if not os.getenv("S3_BUCKET") and (output_dir.resolve().is_relative_to(source) or (os.getenv("BACKUP_WORK_DIR") and Path(os.environ["BACKUP_WORK_DIR"]).resolve().is_relative_to(source))):
        raise BackupError("Backup output and working directories must be outside document storage.")
    with directory_lock(output_dir), workspace() as (work, gpg):
        if not os.getenv("S3_BUCKET") and work.resolve().is_relative_to(source):
            raise BackupError("Temporary backup space must be outside document storage.")
        database = work / "database.dump"
        run(["pg_dump", "--no-password", "--format=custom", "--no-owner", "--no-privileges", "--file", str(database)], env=env)
        revision = query(env, "SELECT version_num FROM alembic_version ORDER BY version_num")
        if not revision:
            raise BackupError("The source database has no migration revision.")
        documents = json.loads(query(env, "SELECT coalesce(json_agg(json_build_object('key',storage_key,'size',byte_size,'sha256',checksum_sha256)), '[]'::json) FROM documents"))
        records = []
        archive = work / "backup.tar"
        def add(tar, path, name):
            if len(records) >= 199_999:
                raise BackupError("This backup exceeds the supported archive file count.")
            record = {"path": name, "size": path.stat().st_size, "sha256": digest(path)}
            tar.add(path, arcname=name, recursive=False)
            records.append(record)
        with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as tar:
            add(tar, database, "database.dump")
            sources = s3_documents(work) if os.getenv("S3_BUCKET") else local_documents(source)
            for key, path in sources:
                add(tar, path, "documents/" + key)
            check_document_inventory(records, documents)
            manifest = {"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                "schema_revisions": revision.splitlines(), "storage_backend": "s3" if os.getenv("S3_BUCKET") else "local", "files": records}
            (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            tar.add(work / "manifest.json", arcname="manifest.json")
        name = f"homexo-backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}.tar.gpg"
        partial = output_dir / (name + ".partial")
        try:
            run(gpg + ["--no-autostart", "--cipher-algo", "AES256", "--compress-algo", "none", "--recipient-file", str(public_key), "--output", str(partial), "--encrypt", str(archive)])
            os.chmod(partial, 0o600)
            with partial.open("rb") as finished:
                os.fsync(finished.fileno())
            final = output_dir / name
            os.link(partial, final)  # Atomic publication without replacing an existing backup.
            partial.unlink()
            fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            partial.unlink(missing_ok=True)
    return {"backup": final.name, "files": len(records), "encrypted_bytes": final.stat().st_size}


def unpack(archive, destination, max_bytes):
    """Validate the complete inventory before extracting regular files to private staging."""
    try:
        with tarfile.open(archive, "r:") as tar:
            members = []
            total = 0
            for member in tar:
                members.append(member)
                total += member.size
                if len(members) > 200_000 or total > max_bytes + 16 * CHUNK:
                    raise BackupError("Archive exceeds its file-count or unpacked-size limit.")
            names = [item.name for item in members]
            if len(names) != len(set(names)) or "manifest.json" not in names or len(names) > 200_000:
                raise BackupError("Invalid or duplicate archive inventory.")
            for member in members:
                safe_key(member.name)
                if not member.isfile() or (member.name not in ("database.dump", "manifest.json") and not member.name.startswith("documents/")):
                    raise BackupError("Archive contains an unexpected path or non-regular file.")
            manifest_member = tar.getmember("manifest.json")
            if manifest_member.size > 16 * CHUNK:
                raise BackupError("Backup manifest is too large.")
            manifest = json.load(tar.extractfile(manifest_member))
            if manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), list):
                raise BackupError("Unsupported backup format.")
            revisions = manifest.get("schema_revisions")
            if not isinstance(revisions, list) or not revisions or not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_]+", value) for value in revisions) or manifest.get("storage_backend") not in ("local", "s3"):
                raise BackupError("Invalid backup schema or storage metadata.")
            inventory = {item["path"]: item for item in manifest["files"]}
            if len(inventory) != len(manifest["files"]) or set(inventory) != set(names) - {"manifest.json"} or "database.dump" not in inventory:
                raise BackupError("Archive and manifest inventory do not match.")
            total = 0
            for member in members:
                if member.name == "manifest.json":
                    continue
                expected = inventory[member.name]
                if not isinstance(expected.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", expected["sha256"]):
                    raise BackupError("Invalid backup checksum metadata.")
                if type(expected["size"]) is not int or expected["size"] != member.size or member.size < 0:
                    raise BackupError("Archive size does not match its manifest.")
                total += member.size
                if total > max_bytes:
                    raise BackupError("Backup exceeds the configured unpacked-size limit.")
            for member in members:
                if member.name == "manifest.json":
                    continue
                target = destination / member.name
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with tar.extractfile(member) as source, target.open("xb") as out:
                    shutil.copyfileobj(source, out, CHUNK)
                os.chmod(target, 0o600)
                if digest(target) != inventory[member.name]["sha256"]:
                    raise BackupError("Backup checksum verification failed.")
            return manifest
    except BackupError:
        raise
    except (tarfile.TarError, ValueError, KeyError, TypeError, AttributeError, OSError):
        raise BackupError("Cannot read a complete, valid backup archive.") from None


@contextlib.contextmanager
def verified_backup(backup, max_bytes):
    private_key = Path(os.getenv("BACKUP_PRIVATE_KEY_FILE", "")).absolute()
    if not private_key.is_file():
        raise BackupError("Set BACKUP_PRIVATE_KEY_FILE to the recovery secret key file.")
    if private_key.stat().st_mode & 0o077:
        raise BackupError("The recovery secret key must be private; use chmod 600.")
    with workspace() as (work, gpg):
        passphrase = os.getenv("BACKUP_KEY_PASSPHRASE_FILE")
        if passphrase:
            if Path(passphrase).stat().st_mode & 0o077:
                raise BackupError("The recovery passphrase file must be private; use chmod 600.")
            gpg += ["--passphrase-file", str(Path(passphrase).absolute())]
        run(gpg + ["--import", str(private_key)])
        archive = work / "backup.tar"
        # Bound decryption before tar inspection, including GnuPG's decompression.
        with tempfile.TemporaryFile() as errors, archive.open("xb") as out:
            with subprocess.Popen(gpg + ["--decrypt", str(Path(backup).absolute())], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors) as process:
                total = 0
                try:
                    for block in iter(lambda: process.stdout.read(CHUNK), b""):
                        total += len(block)
                        if total > max_bytes + 256 * CHUNK:
                            raise BackupError("Decrypted backup exceeds the unpacked-size allowance.")
                        out.write(block)
                except BaseException:
                    process.kill()
                    raise
                if process.wait() != 0:
                    raise BackupError("Backup decryption/integrity verification failed; check the key and archive.")
        staging = work / "verified"
        staging.mkdir(mode=0o700)
        manifest = unpack(archive, staging, max_bytes)
        run(["pg_restore", "--list", str(staging / "database.dump")])
        yield staging, manifest


EMPTY_DATABASE_SQL = """SELECT EXISTS (
 SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
 UNION ALL SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
 UNION ALL SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
 UNION ALL SELECT 1 FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname NOT IN ('public','information_schema')
 UNION ALL SELECT 1 FROM pg_extension WHERE extname <> 'plpgsql'
)"""


def restore(backup, storage_dir, *, writers_stopped=False, max_bytes=100 * 1024**3):
    if not writers_stopped:
        raise BackupError("Keep all recovery API/worker writers stopped and pass --writers-stopped.")
    env = postgres_env(os.getenv("RESTORE_DATABASE_URL", ""))
    target = Path(storage_dir).absolute()
    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
        raise BackupError("Restore requires an empty document directory without symbolic links.")
    with verified_backup(backup, max_bytes) as (staging, manifest):
        if query(env, EMPTY_DATABASE_SQL) != "f":
            raise BackupError("Restore requires an empty database; existing data will not be overwritten.")
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        marker = target / ".restore-in-progress"
        marker.mkdir(mode=0o700)  # Exclusive reservation; a failed restore keeps its marker.
        if set(target.iterdir()) != {marker}:
            raise BackupError("The recovery directory changed; use a fresh empty destination.")
        for item in manifest["files"]:
            if not item["path"].startswith("documents/"):
                continue
            destination = target / item["path"].removeprefix("documents/")
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with (staging / item["path"]).open("rb") as source, destination.open("xb") as out:
                shutil.copyfileobj(source, out, CHUNK)
            os.chmod(destination, 0o600)
        # A failure rolls back all database changes. Staged document copies remain for inspection.
        run(["pg_restore", "--no-password", "--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges",
            "--dbname", env["PGDATABASE"], str(staging / "database.dump")], env=env)
        revisions = query(env, "SELECT version_num FROM alembic_version ORDER BY version_num").splitlines()
        if revisions != manifest["schema_revisions"]:
            raise BackupError("Restored migration revision does not match the backup; keep the recovery API stopped.")
        marker.rmdir()
    return {"restored": True, "files": len(manifest["files"]) - 1, "schema_revisions": revisions, "storage_backend": "local"}


def backup_files(directory):
    result = []
    for path in private_dir(directory).iterdir():
        match = BACKUP_NAME.fullmatch(path.name)
        if match and not path.is_symlink() and path.is_file() and path.stat().st_size > 0:
            try:
                created = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            result.append((created, path))
    return sorted(result, key=lambda item: (item[0], item[1].name))


def status(directory, max_age_hours, *, now=None):
    files = backup_files(directory)
    if not files:
        raise BackupError("No completed encrypted backup exists.")
    now = now or datetime.now(timezone.utc)
    age = (now - files[-1][0]).total_seconds() / 3600
    if age < -0.1 or age > max_age_hours:
        raise BackupError("The latest completed backup is stale or has a future timestamp.")
    return {"latest": files[-1][1].name, "age_hours": round(max(0, age), 2), "recovery_test_required": True}


def prune(directory, keep_days, *, apply=False, now=None):
    directory = private_dir(directory)
    with directory_lock(directory):
        files = backup_files(directory)
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=keep_days)
        expired = [path for created, path in files[:-1] if created < cutoff]
        if apply:
            for path in expired:
                path.unlink()
    return {"dry_run": not apply, "expired": [path.name for path in expired], "kept_latest": bool(files)}


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create", help="Encrypt database and documents with the recovery public key")
    create_parser.add_argument("--output-dir", default=os.getenv("BACKUP_OUTPUT_DIR", "/backups"))
    create_parser.add_argument("--writers-stopped", action="store_true")
    verify_parser = commands.add_parser("verify", help="Decrypt and check inventory, checksums and dump readability")
    restore_parser = commands.add_parser("restore", help="Recover into an empty database and local storage directory")
    for command in (verify_parser, restore_parser):
        command.add_argument("backup")
        command.add_argument("--max-unpacked-gib", type=int, default=100)
    restore_parser.add_argument("--storage-dir", required=True)
    restore_parser.add_argument("--writers-stopped", action="store_true")
    status_parser = commands.add_parser("status", help="Check completed-backup freshness; does not prove restorability")
    prune_parser = commands.add_parser("prune", help="Preview retention; --apply deletes expired copies except the latest")
    for command in (status_parser, prune_parser):
        command.add_argument("--output-dir", default=os.getenv("BACKUP_OUTPUT_DIR", "/backups"))
    status_parser.add_argument("--max-age-hours", type=int, default=26)
    prune_parser.add_argument("--keep-days", type=int, default=30)
    prune_parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        for name in ("max_unpacked_gib", "max_age_hours", "keep_days"):
            if hasattr(args, name) and getattr(args, name) < 1:
                raise BackupError("Size, freshness and retention limits must be positive integers.")
        if args.command == "create":
            result = create(args.output_dir, writers_stopped=args.writers_stopped)
        elif args.command == "verify":
            with verified_backup(args.backup, args.max_unpacked_gib * 1024**3) as (_, manifest):
                result = {"verified": True, "files": len(manifest["files"]), "schema_revisions": manifest["schema_revisions"]}
        elif args.command == "restore":
            result = restore(args.backup, args.storage_dir, writers_stopped=args.writers_stopped, max_bytes=args.max_unpacked_gib * 1024**3)
        elif args.command == "status":
            result = status(args.output_dir, args.max_age_hours)
        else:
            result = prune(args.output_dir, args.keep_days, apply=args.apply)
        print(json.dumps(result))
        return 0
    except (BackupError, OSError) as exc:
        # OSError can mention private paths; print a fixed message for filesystem failures.
        message = str(exc) if isinstance(exc, BackupError) else "Filesystem operation failed; check private paths, permissions and free space."
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
