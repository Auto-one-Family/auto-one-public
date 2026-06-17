#!/bin/bash
set -euo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups"
LOG_DIR="logs/backup"
BACKUP_FILE="${BACKUP_DIR}/automationone_${TIMESTAMP}.sql.gz"
TMP_STDERR="/tmp/automationone_backup_stderr.log"
MAX_RETRIES=3

mkdir -p "${BACKUP_DIR}" "${LOG_DIR}"

log_event() {
  local level="$1"
  local message="$2"
  local attempt="${3:-null}"
  local json_line
  json_line=$(printf '{"ts":"%s","level":"%s","msg":"%s","attempt":%s,"file":"%s"}\n' \
    "$(date -Iseconds)" "$level" "$message" "$attempt" "${BACKUP_FILE}")
  echo "${json_line}" | tee -a "${LOG_DIR}/backup.log"
}

for attempt in $(seq 1 "${MAX_RETRIES}"); do
  log_event "INFO" "backup_attempt" "${attempt}"

  if docker exec automationone-postgres pg_dump \
    -U "${POSTGRES_USER:-god_kaiser}" \
    -d "${POSTGRES_DB:-god_kaiser_db}" \
    > >(gzip > "${BACKUP_FILE}") \
    2>"${TMP_STDERR}"; then
    size_human=$(du -h "${BACKUP_FILE}" | cut -f1)
    printf '{"ts":"%s","level":"INFO","msg":"backup_success","file":"%s","size":"%s"}\n' \
      "$(date -Iseconds)" "${BACKUP_FILE}" "${size_human}" | tee -a "${LOG_DIR}/backup.log"

    # Keep last 7 backups
    ls -1t "${BACKUP_DIR}"/*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
    rm -f "${TMP_STDERR}"
    exit 0
  fi

  error_message=""
  if [ -f "${TMP_STDERR}" ]; then
    error_message=$(tr '\n' ' ' < "${TMP_STDERR}")
  fi

  printf '{"ts":"%s","level":"ERROR","msg":"backup_failed","attempt":%s,"error":"%s"}\n' \
    "$(date -Iseconds)" "${attempt}" "${error_message}" | tee -a "${LOG_DIR}/backup.log"

  if [ "${attempt}" -lt "${MAX_RETRIES}" ]; then
    sleep_seconds=$((2 ** (attempt - 1)))
    printf '{"ts":"%s","level":"WARN","msg":"backup_retry_wait","next_attempt_in_seconds":%s}\n' \
      "$(date -Iseconds)" "${sleep_seconds}" | tee -a "${LOG_DIR}/backup.log"
    sleep "${sleep_seconds}"
  fi
done

rm -f "${BACKUP_FILE}" "${TMP_STDERR}"
printf '{"ts":"%s","level":"ERROR","msg":"backup_exhausted","max_retries":%s}\n' \
  "$(date -Iseconds)" "${MAX_RETRIES}" | tee -a "${LOG_DIR}/backup.log"
exit 1
