# Encrypted backups and recovery

`infra/backup/backup.py` backs up PostgreSQL and all files in the application's local storage directory or configured S3/R2 prefix. It includes quarantined files and generated/signed legal reports, without changing scan status or file permissions in the application. Files referenced by the database must exist and match their recorded sizes/hashes, otherwise the job fails without publishing a backup. Unreferenced storage files are included too.

This is an operator command, not a web endpoint. PostgreSQL custom-format dumps and a SHA-256 inventory are packaged into a tar archive and encrypted with GnuPG using the recovery **public key** and AES-256. Only completed encrypted files are published, atomically. Output directories must be mode `700`; completed files are mode `600`. Job logs contain counts and fixed errors, not database URLs, credentials, document paths or SQL diagnostics.

## Set up

Generate a dedicated encryption-capable OpenPGP key on a recovery workstation, with a strong passphrase. Keep the secret key, passphrase and a tested recovery copy in your organization's vault/offline recovery storage. Export only the public key to the application host. For example, use `gpg --full-generate-key`, then `gpg --armor --export <fingerprint> > backup-public.asc` on that workstation. Confirm the fingerprint out of band before installation. Test that the offline secret key can decrypt a real backup before relying on it.

Create `/srv/homexo-backups` with mode `700`, owned by the backup operator, and put the public key at `/srv/homexo-keys/backup-public.asc`. Set `BACKUP_OUTPUT_DIR` and `BACKUP_PUBLIC_KEY_FILE` in `infra/.env` (copy `.env.example` first). Set `BACKUP_UID`/`BACKUP_GID` to that operator's numeric UID/GID (default `1000:1000`); this account must be able to read the source document volume and public key. The backup container runs as that user so completed files remain accessible to the operator. Relative Compose paths are resolved from `infra/`; absolute host paths are recommended. The maintenance profile is opt-in and exposes no ports.

```bash
docker compose -f infra/docker-compose.yml --profile maintenance build backup
```

The isolated backup image contains PostgreSQL 16 clients, Python, GnuPG and boto3. Use clients matching the database major version; update the image when upgrading PostgreSQL. Native use needs those same tools on `PATH`. `DATABASE_URL` accepts `postgresql://`, `postgres://` and `postgresql+psycopg://`; SSL options are honored. Passwords travel in the child-process environment, not command-line arguments; a URL without a password can use libpq's `PGPASSFILE`. Keep the operator's environment and files private.

## Create and schedule

Database dumps are transactionally consistent, but combining a database and file store requires stopping **all** API and background writers. Do not create a backup while writes, file cleanup, imports, malware rescans, or other deployments sharing the database/storage can run. `--writers-stopped` is an operator assertion, not a system-wide lock.

For the supplied single-API Compose deployment, run:

```bash
bash infra/backup/run-scheduled.sh
```

The wrapper locks out overlapping scheduled jobs, stops the `api` service (including its in-process workers), creates the backup, and restarts the API on success, failure or a normal termination signal. Before restarting writers it stops any surviving container labelled for that job. If it cannot establish/stop that job's state, it leaves the API stopped for operator recovery. It refuses to start an API that was already intentionally stopped. Host failure/SIGKILL still requires manual service recovery. It must run from a checkout with the deployed Compose configuration and the same environment settings. It does not stop independently deployed workers; use your orchestrator's maintenance procedure for those deployments.

Schedule this wrapper daily during an agreed maintenance window, for example `15 2 * * * cd /srv/legali && bash infra/backup/run-scheduled.sh >> /var/log/homexo-backup.log 2>&1` in the operator's crontab. This example uses the host's timezone. Restrict the log file to the operator and monitor nonzero exit codes. A daily schedule gives a nominal RPO of 24 hours; measure the actual restore time for your data size and agree on an RTO. Do not mark production backup readiness complete until scheduling, off-host copying, monitoring and a recovery drill are working.

For a manually stopped deployment:

```bash
docker compose -f infra/docker-compose.yml --profile maintenance run --rm --no-deps backup create --writers-stopped
```

Local files are mounted read-only. For S3/R2, use the same `S3_BUCKET`, endpoint, region, key prefix and read credentials as the API; `ListBucket` and `GetObject` permissions are required. The app uses prefix `homexo/` by default. The tool reads every object under that prefix, checks ETags during fetching, and never writes to the source bucket. Maintain bucket versioning/replication separately where supported. Temporary plaintext dump/archive space is required during backup/recovery; use an encrypted, private working volume (`BACKUP_WORK_DIR` for native commands), with room for the database, archive and staged files. Normal exits clean temporary files; host failure can leave plaintext staging behind. The backup host never needs the recovery secret key.

Copy **completed** `homexo-backup-*.tar.gpg` files to a separate account/host with versioning or object lock. Keep the recovery keys separate. This tool does not provision an off-host destination or transfer files to an unconfigured service. Monitor the copy job as well as the local backup job.

## Freshness and retention

```bash
docker compose -f infra/docker-compose.yml --profile maintenance run --rm --no-deps backup status --max-age-hours 26
docker compose -f infra/docker-compose.yml --profile maintenance run --rm --no-deps backup prune --keep-days 30
# After verifying the off-host copies and recovery policy:
docker compose -f infra/docker-compose.yml --profile maintenance run --rm --no-deps backup prune --keep-days 30 --apply
```

`status` exits nonzero if there is no completed backup or its timestamp is stale/in the future. It is a freshness signal, not a restore test. Retention defaults to a dry run, only considers exact generated filenames, ignores links/partial/unrelated files and always keeps the latest completed copy. It never prunes a source database or source documents. Choose retention with legal/privacy review; backups contain customer records and malware-quarantined files. Avoid retaining customer data indefinitely.

## Verify and recover

Use an isolated recovery host/network with notification delivery, blog jobs and all other workers disabled. Restore only backups from your trusted backup store: a PostgreSQL dump can execute SQL. Preserve the application version/configuration corresponding to the backup, including a separately escrowed `STAFF_MFA_ENCRYPTION_KEY` for authenticator seeds. Secrets and server roles/grants are deliberately not embedded in the backup. Restored objects are owned by the target connection role; reapply your deployment's least-privilege grants. Rotate session/OTP and external provider secrets before exposing a disaster-recovery copy.

Native commands (the key files must be private, mode `600` or stricter):

```bash
export BACKUP_PRIVATE_KEY_FILE=/secure/recovery-secret.asc
export BACKUP_KEY_PASSPHRASE_FILE=/secure/recovery-passphrase
python3 infra/backup/backup.py verify /secure/homexo-backup-YYYYMMDDTHHMMSSZ-xxxxxxxx.tar.gpg

# Create a NEW, empty recovery database through your normal database admin process.
# Inject RESTORE_DATABASE_URL through your vault/environment; never use a live database.
python3 infra/backup/backup.py restore /secure/homexo-backup-YYYYMMDDTHHMMSSZ-xxxxxxxx.tar.gpg \
  --storage-dir /secure/recovered-documents --writers-stopped
```

Omit `BACKUP_KEY_PASSPHRASE_FILE` only for an unprotected test key. Never put private keys or passphrases in repository files, command arguments or a running application's image. The backup image can also run recovery commands with separately mounted read-only key/archive files, a private destination volume and `RESTORE_DATABASE_URL` injected at runtime; its normal Compose service intentionally has no secret key mount.

Verification decrypts the complete archive, validates every regular member against the inventory, rejects traversal paths, links, duplicate/unexpected members and checksum mismatches, and checks `pg_restore --list`. A default 100 GiB expanded-data allowance and 200,000-member ceiling bound recovery resource use; increase `--max-unpacked-gib` deliberately for larger datasets. Verification alone does not execute a restore.

Restore verifies first, refuses any populated target database or document directory, copies documents without overwriting existing files, then restores the database in a single transaction. Failed database imports roll back; any copied files and `.restore-in-progress` marker remain for inspection. Keep the API stopped and use a fresh destination for a retry. A successful restore verifies the migration revision and removes the marker. Restored local documents include all storage keys from either a local or S3-source backup: configure the recovery API with **`S3_BUCKET` empty** and `LOCAL_STORAGE_DIR` pointing at the recovered directory. This tool does not overwrite or restore into an existing S3 bucket.

## Recovery drill

At least monthly, and after schema/storage changes:

1. Fetch an off-host encrypted copy and verify it using the escrowed key.
2. Restore into a newly created disposable PostgreSQL database and empty local directory.
3. Compare case/customer/document counts, migration revision and document SHA-256 values with your backup inventory. Check a sample case, private document download, signed report and staff authenticator access using the corresponding escrowed settings. Keep all outbound delivery disabled.
4. Record backup timestamp, restore duration, results and operator; remove only the disposable database, recovered files and temporary key material after the drill.

Automated regression tests live in `backend/tests/test_backups.py`. The standalone `infra/backup/test_recovery.py` drill exercises real GnuPG with a passphrase-protected key, `pg_dump` and `pg_restore`, row/relationship/document preservation, corrupt archives, wrong keys, missing files, nonempty targets and transactional rollback. It creates and drops only randomly named `homexo_drill_*` databases, uses synthetic data and temporary keys, and starts no API/notification workers.

Run it against a development PostgreSQL instance with `CREATE DATABASE` rights, injecting `BACKUP_TEST_ADMIN_URL` through the environment. With native tools installed, use `python3 infra/backup/test_recovery.py`. Or use the built image (substitute the development database's Docker network):

```bash
docker run --rm --network <development-network> \
  -e BACKUP_TEST_ADMIN_URL -e BACKUP_SCRIPT_DIR=/opt/recovery \
  --mount type=bind,src="$(pwd)/infra/backup/test_recovery.py",dst=/tests/test_recovery.py,readonly \
  --entrypoint python3 infra-backup /tests/test_recovery.py
```

The Compose build normally tags the image `<project>-backup`; replace `infra-backup` above if your Compose project has another name. A skipped drill means it was not run. Never point the application pytest runner's `TEST_DATABASE_URL` at a live database; its fixtures drop tables.
