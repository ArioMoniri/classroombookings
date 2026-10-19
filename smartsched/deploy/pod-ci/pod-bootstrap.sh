#!/usr/bin/env bash
# First boot of the SmartSched pod (root; called by the EC2 user-data after the repo is cloned).
#  1. install pod CI (user, code, units, config)
#  2. deploy/.env: pod values (TLS domain, URLs, sizing for 2 vCPU / 8 GB) and every secret GENERATED
#     HERE on the pod (admin password, APP/JWT/AUTH secrets, Postgres password)
#  3. store admin e-mail/password and app secrets in SSM Parameter Store (SecureString, /smartsched/*)
#  4. /ci/ basic-auth credentials -> SSM /smartsched/ci/basic_auth
#  5. render the /ci/ nginx location, prepare the images (deploy.sh --prepare: no containers, no traffic), start pod
#     CI. There is no ungated first deploy: pod CI's first green run deploys. The deploy-time settings that
#     `smartsched_aws.py up` stored in SSM {prefix}/bootstrap/* (institution name, AI key, SMTP, security contact,
#     calendar OAuth clients, OBSERVABILITY) reach deploy.sh from pod CI's deploy step as environment variables, never
#     as arguments; it writes them into the database once (seed/bootstrap_settings.py).
# Re-running it is safe: an existing .env keeps its secrets and is re-synced to SSM.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$HERE/../../.." && pwd)"
DEPLOY="$SRC/smartsched/deploy"
: "${SMARTSCHED_PANEL_DOMAIN:?}" "${SMARTSCHED_ADMIN_EMAIL:?}" "${SMARTSCHED_ACME_EMAIL:?}"
DOMAIN="$SMARTSCHED_PANEL_DOMAIN"

bash "$HERE/install.sh" --no-start
chown -R smartsched-ci:smartsched-ci "$(dirname "$SRC")"
as_ci() {
  runuser -u smartsched-ci -- env PYTHONPATH=/opt/smartsched-ci PYTHONDONTWRITEBYTECODE=1 \
    PODCI_CONFIG=/etc/smartsched-ci/ci.env HOME=/var/lib/smartsched-ci "$@"
}

as_ci python3 -m podci prepare-env "$DEPLOY/.env" "$DEPLOY/.env.example" \
  ENVIRONMENT=prod \
  "PUBLIC_URL=https://${DOMAIN}" \
  "CORS_ORIGINS=[\"https://${DOMAIN}\"]" \
  "TLS_DOMAIN=${DOMAIN}" \
  "ACME_EMAIL=${SMARTSCHED_ACME_EMAIL}" \
  "ADMIN_EMAIL=${SMARTSCHED_ADMIN_EMAIL}" \
  PROXY_BIND=127.0.0.1 \
  UVICORN_WORKERS=2 SOLVER_WORKERS=2 BACKEND_CPUS=2 BACKEND_MEMORY=3g \
  FRONTEND_CPUS=1 FRONTEND_MEMORY=1g DB_CPUS=1 DB_MEMORY=1g
as_ci python3 -m podci sync-secrets "$DEPLOY/.env"
as_ci python3 -m podci basic-auth /var/lib/smartsched-ci/basic_auth
as_ci python3 -m podci render-nginx "$DEPLOY/nginx/default.conf"

# No ungated deploy here: the first deploy is pod CI's first green run (every gate, then gates/deploy.sh, which also
# hands the deploy-time settings from SSM {prefix}/bootstrap/* to deploy.sh). This only prepares images so that run's
# deploy is faster: `deploy.sh --prepare` pulls and builds, never starts a container and never writes deployed-sha
# (so smartsched-stack.service reports "first deploy pending" until then).
# deploy-time settings from SSM (values never printed; the file is the CI user's, 0600, deleted afterwards): the
# prepare writes OBSERVABILITY into .env once (it decides the image set), nothing else is applied here
BOOT_ENV=/var/lib/smartsched-ci/bootstrap.env
as_ci python3 -m podci bootstrap-env "$BOOT_ENV" || { echo "[pod-bootstrap] no deploy-time settings read"; : > "$BOOT_ENV"; }
echo "[pod-bootstrap] preparing images (no containers started; the first green pod CI run deploys)"
if ! as_ci bash -c "set -a; . '$BOOT_ENV'; set +a; cd '$DEPLOY' && ./deploy.sh --prepare --tls"; then
  echo "[pod-bootstrap] image preparation failed; the first pod CI deploy builds them"
fi
rm -f "$BOOT_ENV"

systemctl enable --now smartsched-ci-web.service smartsched-ci-poll.timer smartsched-ci-worker.timer \
  smartsched-ci-worker.path smartsched-ci-update.path smartsched-upload-purge.timer smartsched-backup.timer
systemctl enable smartsched-stack.service
echo "[pod-bootstrap] panel https://${DOMAIN}  CI https://${DOMAIN}/ci/"
echo "[pod-bootstrap] admin ${SMARTSCHED_ADMIN_EMAIL}; password in SSM ${SMARTSCHED_SSM_PREFIX:-/smartsched}/admin_password"
