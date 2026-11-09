"""Real PostgreSQL/GnuPG drill. Requires BACKUP_TEST_ADMIN_URL and CREATE DATABASE rights.

Only randomly named databases created by this test are dropped. No live API is started.
Run in the backup image with this file mounted read-only; see docs/backups.md.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, os.getenv("BACKUP_SCRIPT_DIR", str(Path(__file__).parent)))
import backup


@unittest.skipUnless(os.getenv("BACKUP_TEST_ADMIN_URL"), "Set BACKUP_TEST_ADMIN_URL to a development PostgreSQL instance")
class RecoveryDrill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="homexo-drill-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.admin = backup.postgres_env(os.environ["BACKUP_TEST_ADMIN_URL"])
        cls.source_name = "homexo_drill_src_" + uuid.uuid4().hex[:12]
        backup.query(cls.admin, 'CREATE DATABASE "' + cls.source_name + '"')
        cls.addClassCleanup(backup.query, cls.admin, 'DROP DATABASE "' + cls.source_name + '"')
        parsed = urlsplit(os.environ["BACKUP_TEST_ADMIN_URL"])
        cls.source_url = urlunsplit(parsed._replace(path="/" + cls.source_name))
        cls.source_env = backup.postgres_env(cls.source_url)
        cls.document_data = b"Synthetic case evidence for encrypted restore verification.\n"
        checksum = hashlib.sha256(cls.document_data).hexdigest()
        backup.query(cls.source_env, """
CREATE TABLE alembic_version (version_num varchar(64) PRIMARY KEY);
INSERT INTO alembic_version VALUES ('0021_api_abuse_protection');
CREATE TABLE customers (id integer PRIMARY KEY, full_name text);
INSERT INTO customers VALUES (1, 'Synthetic Recovery Customer');
CREATE TABLE service_requests (id integer PRIMARY KEY, customer_id integer REFERENCES customers(id), ticket_number text UNIQUE);
INSERT INTO service_requests VALUES (1, 1, 'HX-RECOVERY-TEST');
CREATE TABLE documents (id integer PRIMARY KEY, service_request_id integer REFERENCES service_requests(id), storage_key text, byte_size bigint, checksum_sha256 text, scan_status text);
INSERT INTO documents VALUES (1, 1, 'tickets/HX-RECOVERY-TEST/document.pdf', %d, '%s', 'clean');
CREATE TABLE audit_logs (id integer PRIMARY KEY, event text);
INSERT INTO audit_logs VALUES (1, 'Synthetic recovery evidence');
""" % (len(cls.document_data), checksum))
        cls.documents = cls.root / "source-documents"
        cls.document = cls.documents / "tickets/HX-RECOVERY-TEST/document.pdf"
        cls.document.parent.mkdir(parents=True)
        cls.document.write_bytes(cls.document_data)
        cls.output = cls.root / "encrypted"
        cls.output.mkdir(mode=0o700)
        cls.work = cls.root / "work"
        cls.work.mkdir(mode=0o700)
        cls.gpg_home = cls.root / "key-generation"
        cls.gpg_home.mkdir(mode=0o700)
        cls.passphrase = cls.root / "key-passphrase"
        cls.passphrase.write_text("synthetic-recovery-test-passphrase\n")
        cls.passphrase.chmod(0o600)
        gpg = ["gpg", "--no-options", "--homedir", str(cls.gpg_home), "--batch", "--pinentry-mode", "loopback", "--passphrase-file", str(cls.passphrase)]
        cls.addClassCleanup(subprocess.run, ["gpgconf", "--homedir", str(cls.gpg_home), "--kill", "all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        backup.run(gpg + ["--quick-generate-key", "Homexo synthetic recovery test", "rsa2048", "encr", "1d"])
        fingerprint = next(line.split(":")[9] for line in backup.run(gpg + ["--with-colons", "--list-keys"], output=True).splitlines() if line.startswith("fpr:"))
        cls.public = cls.root / "public.asc"
        cls.secret = cls.root / "secret.asc"
        backup.run(gpg + ["--armor", "--output", str(cls.public), "--export", fingerprint])
        backup.run(gpg + ["--armor", "--output", str(cls.secret), "--export-secret-keys", fingerprint])
        cls.secret.chmod(0o600)
        cls.environment = patch.dict(os.environ, {"DATABASE_URL": cls.source_url, "LOCAL_STORAGE_DIR": str(cls.documents), "S3_BUCKET": "", "BACKUP_PUBLIC_KEY_FILE": str(cls.public), "BACKUP_PRIVATE_KEY_FILE": str(cls.secret), "BACKUP_KEY_PASSPHRASE_FILE": str(cls.passphrase), "BACKUP_WORK_DIR": str(cls.work)})
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        # Creation only needs the public key. Do not expose the secret to the backup command.
        with patch.dict(os.environ, {"BACKUP_PRIVATE_KEY_FILE": ""}):
            result = backup.create(cls.output, writers_stopped=True)
        cls.archive = cls.output / result["backup"]

    def setUp(self):
        self.target_name = "homexo_drill_dst_" + uuid.uuid4().hex[:12]
        backup.query(self.admin, 'CREATE DATABASE "' + self.target_name + '"')
        self.addCleanup(backup.query, self.admin, 'DROP DATABASE "' + self.target_name + '"')
        parsed = urlsplit(os.environ["BACKUP_TEST_ADMIN_URL"])
        target_url = urlunsplit(parsed._replace(path="/" + self.target_name))
        self.target_env = backup.postgres_env(target_url)
        self.target_setting = patch.dict(os.environ, {"RESTORE_DATABASE_URL": target_url})
        self.target_setting.start()
        self.addCleanup(self.target_setting.stop)
        self.destination = self.root / self.target_name

    def test_real_encrypted_restore_preserves_rows_foreign_keys_and_document_bytes(self):
        self.assertEqual(self.archive.stat().st_mode & 0o077, 0)
        self.assertNotIn(self.document_data, self.archive.read_bytes())
        with backup.verified_backup(self.archive, 1024**3) as (_, manifest):
            self.assertEqual(len(manifest["files"]), 2)
        result = backup.restore(self.archive, self.destination, writers_stopped=True)
        self.assertTrue(result["restored"])
        self.assertEqual(backup.query(self.target_env, "SELECT c.full_name || ':' || r.ticket_number FROM customers c JOIN service_requests r ON c.id=r.customer_id"), "Synthetic Recovery Customer:HX-RECOVERY-TEST")
        self.assertEqual(backup.query(self.target_env, "SELECT count(*) FROM audit_logs"), "1")
        self.assertEqual((self.destination / "tickets/HX-RECOVERY-TEST/document.pdf").read_bytes(), self.document_data)
        self.assertEqual(backup.query(self.target_env, "SELECT scan_status FROM documents"), "clean")
        self.assertFalse((self.destination / ".restore-in-progress").exists())
        self.assertEqual(list(self.work.iterdir()), [])

    def test_populated_database_is_never_overwritten(self):
        backup.query(self.target_env, "CREATE TABLE sentinel (value integer); INSERT INTO sentinel VALUES (42)")
        with self.assertRaisesRegex(backup.BackupError, "empty database"):
            backup.restore(self.archive, self.destination, writers_stopped=True)
        self.assertEqual(backup.query(self.target_env, "SELECT value FROM sentinel"), "42")
        self.assertFalse(self.destination.exists())

    def test_existing_document_files_are_never_overwritten(self):
        self.destination.mkdir()
        (self.destination / "sentinel").write_bytes(b"keep")
        with self.assertRaisesRegex(backup.BackupError, "empty document"):
            backup.restore(self.archive, self.destination, writers_stopped=True)
        self.assertEqual((self.destination / "sentinel").read_bytes(), b"keep")
        self.assertEqual(backup.query(self.target_env, backup.EMPTY_DATABASE_SQL), "f")

    def test_corrupt_encrypted_archive_fails_before_touching_targets(self):
        corrupt = self.root / "truncated.tar.gpg"
        corrupt.write_bytes(self.archive.read_bytes()[:-32])
        with self.assertRaises(backup.BackupError):
            backup.restore(corrupt, self.destination, writers_stopped=True)
        self.assertEqual(backup.query(self.target_env, backup.EMPTY_DATABASE_SQL), "f")
        self.assertFalse(self.destination.exists())

    def test_wrong_secret_key_cannot_decrypt(self):
        other = self.root / "wrong-secret.asc"
        gpg = ["gpg", "--no-options", "--homedir", str(self.gpg_home), "--batch", "--pinentry-mode", "loopback", "--passphrase-file", str(self.passphrase)]
        backup.run(gpg + ["--quick-generate-key", "Wrong synthetic recovery key", "rsa2048", "encr", "1d"])
        fingerprints = [line.split(":")[9] for line in backup.run(gpg + ["--with-colons", "--list-keys"], output=True).splitlines() if line.startswith("fpr:")]
        backup.run(gpg + ["--armor", "--output", str(other), "--export-secret-keys", fingerprints[-1]])
        other.chmod(0o600)
        with patch.dict(os.environ, {"BACKUP_PRIVATE_KEY_FILE": str(other)}):
            with self.assertRaises(backup.BackupError):
                backup.restore(self.archive, self.destination, writers_stopped=True)
        self.assertFalse(self.destination.exists())

    def test_missing_source_document_publishes_no_backup(self):
        self.document.unlink()
        try:
            with self.assertRaisesRegex(backup.BackupError, "referenced document"):
                backup.create(self.output, writers_stopped=True)
        finally:
            self.document.write_bytes(self.document_data)
        self.assertEqual([path.name for path in self.output.glob("*.tar.gpg")], [self.archive.name])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_failed_import_rolls_back_all_earlier_restore_statements(self):
        original_run = backup.run
        def inject_conflict(command, **kwargs):
            if command[0] == "pg_restore" and "--single-transaction" in command:
                backup.query(self.target_env, "CREATE TABLE customers (sentinel integer); INSERT INTO customers VALUES (42)")
            return original_run(command, **kwargs)
        with patch.object(backup, "run", inject_conflict):
            with self.assertRaises(backup.BackupError):
                backup.restore(self.archive, self.destination, writers_stopped=True)
        self.assertEqual(backup.query(self.target_env, "SELECT sentinel FROM customers"), "42")
        self.assertEqual(backup.query(self.target_env, "SELECT to_regclass('public.alembic_version') IS NULL"), "t")
        self.assertTrue((self.destination / ".restore-in-progress").exists())


if __name__ == "__main__":
    os.umask(0o077)
    unittest.main(verbosity=2)
