#!/usr/bin/env bash
# One job per deployment. All application writers must run in the api service.
set -euo pipefail
umask 077
backup_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
backup_compose_file="$backup_script_dir/../docker-compose.yml"
exec 9>"$backup_script_dir/.schedule.lock"
flock -n 9 || { echo 'Another scheduled backup is running.' >&2; exit 75; }
compose=(docker compose -f "$backup_compose_file")
backup_restart_api=false
backup_job_id="${BASHPID}-${RANDOM}-${RANDOM}"
backup_run_name="homexo-backup-job-$backup_job_id"
restart_api() {
  local result=$?
  trap - EXIT
  # A signal can interrupt Compose while its attached container is still running.
  # Remove only this job's labelled container before allowing writers to restart.
  local remaining
  if ! remaining="$(docker ps -aq --filter "label=com.homexo.backup-job=$backup_job_id" --filter "name=^/$backup_run_name$" )"; then
    echo 'Cannot establish backup job state; keep the API stopped and inspect the Docker daemon.' >&2
    exit 1
  fi
  if [[ -n "$remaining" ]]; then
    if ! docker stop --time 30 "$remaining"; then
      if ! remaining="$(docker ps -q --filter "label=com.homexo.backup-job=$backup_job_id" --filter "name=^/$backup_run_name$" )" || [[ -n "$remaining" ]]; then
        echo 'Cannot stop the interrupted backup; keep the API stopped and inspect the job.' >&2
        exit 1
      fi
    fi
    # --rm normally removed it already. A stopped leftover is harmless to the snapshot.
    if [[ -n "$remaining" ]]; then docker rm -f "$remaining" >/dev/null 2>&1 || true; fi
  fi
  if "$backup_restart_api"; then
    if ! "${compose[@]}" start api; then
      echo 'Backup job could not restart the API; restore service manually.' >&2
      result=1
    fi
  fi
  exit "$result"
}
trap restart_api EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
backup_running_services="$("${compose[@]}" ps --status running --services)"
if ! [[ $'\n'"$backup_running_services"$'\n' == *$'\napi\n'* ]]; then
  echo 'The API is already stopped; use the manual maintenance procedure.' >&2
  exit 1
fi
# Set the recovery action first so even an interrupted stop attempts to restore service.
backup_restart_api=true
"${compose[@]}" stop api
backup_writer_ids="$("${compose[@]}" ps --status running -q api)"
if [[ -n "$backup_writer_ids" ]]; then
  echo 'API writers are still running; backup aborted.' >&2
  exit 1
fi
"${compose[@]}" --profile maintenance run --rm --no-deps --name "$backup_run_name" \
  --label "com.homexo.backup-job=$backup_job_id" backup create --writers-stopped
# Retention is separate: verify off-host copies/recovery before deleting old backups.
