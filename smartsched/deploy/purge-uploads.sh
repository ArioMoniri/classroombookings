#!/usr/bin/env bash
# Retention purge for stored uploads (docs/review/2026-10-15-phase19-engineering.md P19-Q3, KVKK): deletes files
# under the backend's UPLOAD_DIR older than UPLOAD_RETENTION_DAYS (default 30) - source workbooks
# (uploads/imports) and intake documents - and the job directories left empty. uploads/rooms (room photos, the
# organisation logo: public assets) is never purged (UPLOAD_RETENTION_KEEP, space separated, default "rooms").
#
#   purge-uploads.sh [--days N] [--dry-run] [--deploy-dir DIR]
#       runs itself in a one-off backend container (docker compose run --no-deps: works while the backend is
#       stopped) so the path is the container's own UPLOAD_DIR and the files are deleted as the backend user
#   purge-uploads.sh --dir DIR [--days N] [--dry-run]     the same purge on a local directory
#
# The pod runs it daily (pod-ci/systemd/smartsched-upload-purge.timer, Persistent=true: after an idle stop it
# runs at the next boot). Elsewhere: cron, e.g. `17 3 * * * /opt/smartsched/src/smartsched/deploy/purge-uploads.sh`.
set -euo pipefail

days="" dry=0 dir="" mode=compose deploy_dir=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days) days="${2:-}"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    --dir) dir="${2:-}"; mode=local; shift 2 ;;
    --in-container) mode=local; dir="${UPLOAD_DIR:?UPLOAD_DIR is not set in the backend container}"; shift ;;
    --deploy-dir) deploy_dir="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ "$mode" == compose ]]; then
  cd "${deploy_dir:-$(dirname "${BASH_SOURCE[0]}")}"
  if [[ -z "$days" && -f .env ]]; then
    days="$(grep -E '^UPLOAD_RETENTION_DAYS=' .env | tail -n 1 | cut -d= -f2- | tr -d '"'"'"' ')" || true
  fi
  args=(--in-container --days "${days:-30}")
  [[ $dry -eq 1 ]] && args+=(--dry-run)
  exec docker compose --env-file .env -f docker-compose.yml run --rm --no-deps -T --entrypoint bash \
    -e UPLOAD_RETENTION_KEEP="${UPLOAD_RETENTION_KEEP:-rooms}" backend -s -- "${args[@]}" < "${BASH_SOURCE[0]}"
fi

days="${days:-30}"
if ! [[ "$days" =~ ^[0-9]+$ ]] || (( days < 1 )); then
  echo "--days must be a positive number of days (got '$days')" >&2; exit 2
fi
if [[ ! -d "$dir" ]]; then echo "no upload directory at $dir; nothing to purge"; exit 0; fi
dir="$(cd "$dir" && pwd -P)"
if [[ "$dir" == / ]]; then echo "refusing to purge /" >&2; exit 2; fi

excl=()
for k in ${UPLOAD_RETENTION_KEEP:-rooms}; do excl+=(-not -path "$dir/$k" -not -path "$dir/$k/*"); done
mapfile -t old < <(find "$dir" -mindepth 1 -type f -mmin "+$(( days * 1440 ))" "${excl[@]}" -print | sort)
if [[ $dry -eq 1 ]]; then
  for f in ${old[@]+"${old[@]}"}; do echo "would remove ${f#"$dir"/}"; done
  echo "dry run: ${#old[@]} file(s) older than $days days in $dir (kept: ${UPLOAD_RETENTION_KEEP:-rooms})"
  exit 0
fi
for f in ${old[@]+"${old[@]}"}; do rm -f -- "$f"; done
# the helper's encrypted file stages (HB-23b) live at most 10 minutes; the backend sweeps them every 15 s too
if [[ -d "$dir/helper-stage" ]]; then find "$dir/helper-stage" -type f -mmin +10 -delete; fi
# job directories emptied by the purge (top-level directories such as imports/ stay)
find "$dir" -mindepth 2 -type d -empty "${excl[@]}" -delete
echo "removed ${#old[@]} file(s) older than $days days from $dir (kept: ${UPLOAD_RETENTION_KEEP:-rooms})"
