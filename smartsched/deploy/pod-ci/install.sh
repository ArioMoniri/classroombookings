#!/usr/bin/env bash
# Install / upgrade pod CI on the SmartSched pod (root). Called by pod-bootstrap.sh on first boot and by
# smartsched-ci-update.service after every successful deploy (--upgrade).
#   install.sh [--no-start] [--upgrade]
# Creates the smartsched-ci system user (docker group), /var/lib/smartsched-ci (SQLite state, logs,
# caches), copies podci/ + gates/ to /opt/smartsched-ci (atomic swap), installs the systemd units and
# writes /etc/smartsched-ci/ci.env once (from ci.env.example + SMARTSCHED_* values of the user-data).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NO_START=0
UPGRADE=0
for arg in "$@"; do
  case "$arg" in
    --no-start) NO_START=1 ;;
    --upgrade) UPGRADE=1 ;;
    *) echo "unknown flag $arg" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "install.sh must run as root" >&2; exit 1; }
CI_USER=smartsched-ci
STATE=/var/lib/smartsched-ci
DEST=/opt/smartsched-ci
CONF=/etc/smartsched-ci/ci.env

getent group docker >/dev/null || groupadd --system docker
if ! id "$CI_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin --user-group --groups docker "$CI_USER"
fi
install -d -o "$CI_USER" -g "$CI_USER" -m 750 "$STATE" "$STATE/logs" "$STATE/work" "$STATE/cache"
touch "$STATE/queue-signal" "$STATE/update-request"
chown "$CI_USER:$CI_USER" "$STATE/queue-signal" "$STATE/update-request"

# Code: atomic directory swap so a running worker never sees a half-copied tree.
rm -rf "$DEST.new"
install -d -m 755 "$DEST.new"
cp -r "$HERE/podci" "$HERE/gates" "$DEST.new/"
find "$DEST.new" -name '__pycache__' -prune -exec rm -rf {} +
chmod 755 "$DEST.new"/gates/*.sh
if [[ -d "$DEST" ]]; then mv "$DEST" "$DEST.old"; fi
mv "$DEST.new" "$DEST"
rm -rf "$DEST.old"

# Config: written once; later edits on the pod are kept.
if [[ ! -f "$CONF" ]]; then
  install -d -m 755 "$(dirname "$CONF")"
  cp "$HERE/ci.env.example" "$CONF"
  set_conf() { [[ -n "$2" ]] && sed -i "s|^$1=.*|$1=$2|" "$CONF"; return 0; }
  set_conf PODCI_REPO "${SMARTSCHED_REPO:-}"
  set_conf PODCI_BRANCHES "${SMARTSCHED_CI_BRANCHES:-}"
  set_conf PODCI_DEPLOY_BRANCH "${SMARTSCHED_DEPLOY_BRANCH:-}"
  set_conf PODCI_SSM_PREFIX "${SMARTSCHED_SSM_PREFIX:-}"
  set_conf PODCI_IDLE_ALARM "${SMARTSCHED_IDLE_ALARM:-}"
  set_conf PODCI_IDLE_MINUTES "${SMARTSCHED_IDLE_MINUTES:-}"
  set_conf PODCI_IDLE_CPU "${SMARTSCHED_IDLE_CPU:-}"
  if [[ -n "${SMARTSCHED_PANEL_DOMAIN:-}" ]]; then set_conf PODCI_PUBLIC_URL "https://${SMARTSCHED_PANEL_DOMAIN}"; fi
  chmod 644 "$CONF"
fi

install -m 644 "$HERE"/systemd/*.service "$HERE"/systemd/*.timer "$HERE"/systemd/*.path /etc/systemd/system/
systemctl daemon-reload
if [[ $NO_START -eq 0 ]]; then
  systemctl enable --now smartsched-ci-web.service smartsched-ci-poll.timer smartsched-ci-worker.timer \
    smartsched-ci-worker.path smartsched-ci-update.path
  if [[ $UPGRADE -eq 1 ]]; then systemctl restart smartsched-ci-web.service; fi
fi
echo "pod CI installed in $DEST (state $STATE, config $CONF)"
