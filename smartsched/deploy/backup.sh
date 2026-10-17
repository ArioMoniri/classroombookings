#!/usr/bin/env bash
# Nightly backup of the SmartSched state: the PostgreSQL database (pg_dump -Fc) and the uploads volume, kept
# BACKUP_KEEP_DAYS (14) days in BACKUP_DIR (/var/backups/smartsched). After a successful run it writes the
# Prometheus textfile metric smartsched_backup_last_success_timestamp_seconds into TEXTFILE_DIR
# (/var/lib/smartsched/textfile, read by Alloy in the observability profile; alert SmartSchedBackupStale > 26 h).
#
#   /etc/cron.d/smartsched-backup:
#   30 2 * * * root /opt/classroombookings/smartsched/deploy/backup.sh >> /var/log/smartsched-backup.log 2>&1
#
# Env: ENV_FILE (deploy/.env), BACKUP_DIR, BACKUP_KEEP_DAYS, TEXTFILE_DIR, BACKUP_ALPINE_IMAGE.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/smartsched}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/var/lib/smartsched/textfile}"
ALPINE="${BACKUP_ALPINE_IMAGE:-alpine:3.24}"

env_get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//'; }

[[ -f "$ENV_FILE" ]] || { echo "[backup] no $ENV_FILE" >&2; exit 1; }
project="$(env_get COMPOSE_PROJECT_NAME)"; project="${project:-smartsched}"
pg_user="$(env_get POSTGRES_USER)"; pg_user="${pg_user:-smartsched}"
pg_db="$(env_get POSTGRES_DB)"; pg_db="${pg_db:-smartsched}"
day="$(date +%F)"
mkdir -p "$BACKUP_DIR"

echo "[backup] $(date -u +%FT%TZ) database $pg_db"
docker compose --env-file "$ENV_FILE" -f "$HERE/docker-compose.yml" exec -T db \
  pg_dump -U "$pg_user" -Fc "$pg_db" > "$BACKUP_DIR/db-$day.dump.part"
mv "$BACKUP_DIR/db-$day.dump.part" "$BACKUP_DIR/db-$day.dump"

echo "[backup] uploads volume ${project}_uploads"
docker run --rm -v "${project}_uploads:/u:ro" -v "$BACKUP_DIR:/b" "$ALPINE" tar czf "/b/uploads-$day.tgz" -C /u .

find "$BACKUP_DIR" -type f \( -name 'db-*.dump' -o -name 'uploads-*.tgz' \) -mtime +"$KEEP" -delete

# success marker for Prometheus (atomic rename: Alloy never reads a half-written file)
if mkdir -p "$TEXTFILE_DIR" 2>/dev/null; then
  printf '# HELP smartsched_backup_last_success_timestamp_seconds last successful backup (unix time)\n# TYPE smartsched_backup_last_success_timestamp_seconds gauge\nsmartsched_backup_last_success_timestamp_seconds %s\n' "$(date +%s)" \
    > "$TEXTFILE_DIR/backup.prom.tmp" && mv "$TEXTFILE_DIR/backup.prom.tmp" "$TEXTFILE_DIR/backup.prom"
fi
echo "[backup] done: $BACKUP_DIR/db-$day.dump, uploads-$day.tgz"
