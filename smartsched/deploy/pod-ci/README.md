# Pod CI (CI that runs on the SmartSched AWS pod)

GitHub Actions minutes are not used for CI. The pod polls GitHub, runs the same gates as
`.github/workflows/smartsched.yml` (now manual-only) inside Docker on the pod, posts commit statuses
(the ✓/✗ next to a commit or PR), redeploys the deploy branch when it is green, and shows the results at
`https://<panel>/ci/`. There is no runner registration and no GitHub-hosted runner.

```
systemd timer (2 min) -> podci poll -> git ls-remote (token from SSM) -> new head? -> SQLite queue
                                     -> heartbeat metrics + idle check
path unit (queue-signal) -> podci work (flock, one job at a time)
    prepare -> validate -> backend -> infra -> frontend -> e2e-real -> parity -> planner -> images -> watchdog
    -> deploy (deploy branch only, all blocking gates green, commit still the branch head)
    -> POST /repos/{owner}/{repo}/statuses/{sha} per gate + overall ("pod-ci", "pod-ci/<gate>")
nginx /ci/ -> 172.17.0.1:8095 -> podci web (admin JWT cookie or basic auth)
```

## Gates

| Gate | Where | What | Blocking |
|---|---|---|---|
| `prepare` | host | builds `smartsched-podci-python:<hash>` (backend base image + make/git/PyYAML), pulls `mcr.microsoft.com/playwright:v<locked version>-noble` | yes |
| `validate` | host | `smartsched/deploy/validate.sh`, then the docs check: `python3 -I scripts/docs/sync_docs.py --check` (every generated `<!-- AUTO:... -->` block matches its source) and the generator's unit tests | yes |
| `backend` | python CI container | `make check` (PostgreSQL tests against a `postgres` service container: the compose-pinned image, tmpfs, `TEST_POSTGRES_URL`), solver gate, AI gate, exactly one Alembic head, fresh `alembic upgrade head` on SQLite and PostgreSQL; installs with `requirements.lock` as constraints | yes |
| `infra` | python CI container | ruff + pytest for `infra/aws` and this directory | yes |
| `frontend` | Playwright container | `npm ci`, `npm run check` (tsc + eslint + vitest) | yes |
| `e2e-real` | backend + Playwright containers on a per-run network | backend imports the real Bahar, Güz 2026-27 and Final fixtures (`tests/fixtures/*.xlsx`) and the room master, seeds the admin, publishes the Bahar and Güz imported boards and seeds the analytics runs (`gates/e2e-seed-analytics.py`), solves the full Bahar term, serves with the booking clock pinned inside Bahar 2026 (`gates/e2e-backend-entry.sh`); `E2E_REAL=1 npx playwright test` runs every spec (smoke, real-backend, bookings, calendar, motion-audit), then the standalone build is checked for mock/demo code (`validate.sh --no-mock-build`). There is no mock-API gate. Also on the network: `smtp` (`gates/smtp-sink.py`: SMTP 1025, JSON API 8025, nothing delivered) and `backend-empty` (an empty database, no users: the first-run installer). Playwright gets `E2E_SMTP_HOST/PORT/API` and `E2E_EMPTY_API_URL`. A booking clock outside Bahar 2026 fails the gate before any spec runs. | yes |
| `parity` | python CI container | `scripts/parity_check.py` (CRBS superset): API rows run here, UI rows are judged by this run's `/w/playwright-report.json` (skipped / failed / not run = FAIL; no report = gate fails) | yes |
| `planner` | python CI container | `tools/validate_planner.py` on the real workbooks (4 solves) | yes |
| `images` | host | `docker build` backend, frontend, legacy CRBS (no push; tags removed, cache kept); the backend image must import the intake parsers | yes |
| `watchdog` | python CI container | `scripts/watchdog.py` report | no |
| `deploy` | host | checkout the commit in `/opt/smartsched/src`, render `/ci/` into nginx, `deploy.sh --update --no-pull --tls`, restart proxy, health check, then self-update pod CI | yes (deploy branch) |

Containers run as the `smartsched-ci` uid with `--cpus 2 --memory 3g`, `no-new-privileges`, and are
removed afterwards. The gates run strictly one after another (never in parallel) on a 2 vCPU / 8 GB arm64
t4g.large that also serves the app (~2 GB). Node containers (`frontend`, the Playwright container of `e2e-real`)
get `NODE_MEMORY` (4g) and `NODE_OPTIONS=--max-old-space-size=$NODE_HEAP_MB` (3072): V8's default heap ran out
in run #51 ("Ineffective mark-compacts near heap limit"). Under `CI=1` `vitest.config.mts` uses at most 2 forks
with a 1536 MB heap each and a 30 s test timeout; Playwright runs `--workers=1`; in `e2e-real` the SMTP sink is
capped at 256m and the empty backend at 1g. The frontend image build sets the `next build` heap
(`NODE_BUILD_HEAP_MB`, 3072). No test is skipped to save memory. A gate whose `needs` failed is skipped (reported as `error`, never green).
The stack smoke test of the Actions workflow is replaced by the real deploy plus its health check.

## Files

| Path | Purpose |
|---|---|
| `podci/` | the service (stdlib + `python3-boto3`): `state.py` SQLite state machine, `runner.py` poller/worker/heartbeat, `github.py` statuses, `gitops.py` token-in-header git, `web.py` `/ci/`, `nginx.py`, `envfile.py`, `disk.py`, `cloud.py` |
| `gates/*.sh` | one script per gate (host side, starts its own containers) |
| `systemd/` | `smartsched-ci-poll.{service,timer}`, `smartsched-ci-worker.{service,path,timer}`, `smartsched-ci-web.service`, `smartsched-ci-update.{service,path}`, `smartsched-stack.service` (boot: the last good app stack, `gates/stack-up.sh`), `smartsched-upload-purge.{service,timer}` (daily `../purge-uploads.sh`, `Persistent=true` so a purge missed during an idle stop runs after the next boot) |
| `install.sh` | root: user, `/var/lib/smartsched-ci`, `/opt/smartsched-ci` (atomic swap), units, `/etc/smartsched-ci/ci.env` |
| `pod-bootstrap.sh` | first boot: `.env` with secrets generated on the pod, SSM sync, `/ci/` basic auth, first deploy, start CI |
| `ci.env.example` | configuration keys (`PODCI_*`) |

## Behaviour

- **One job at a time**: the worker holds `worker.lock` (flock). A new commit on a branch supersedes its
  queued (not running) predecessors; their status becomes `error: superseded`.
- **Restart-safe**: state lives in `/var/lib/smartsched-ci/ci.sqlite3` (WAL). A run left `running` by a
  killed worker is requeued once (`PODCI_MAX_ATTEMPTS`, default 2), then marked `error`. Leftover
  containers and networks (label `smartsched-ci.run`) are removed when a worker starts.
- **Deploy only when safe**: all blocking gates green and the commit is still the head of the deploy
  branch. The pod's deploy checkout is detached at the tested SHA (`deploy.sh --no-pull`).
- **A failure never takes the live stack down**: a failed gate never reaches `deploy.sh`; `deploy.sh --update`
  builds first and then `up -d` (never `down`), so a failed build leaves the running containers alone. A failed
  deploy (build, migrations, health) is rolled back: the deploy checkout goes back to the last good commit
  (`/var/lib/smartsched-ci/deployed-sha`, written after every healthy deploy and by `pod-bootstrap.sh`) and
  `deploy.sh` runs again for it; the deploy status says `rolled back to <sha>` (or that there was nothing to roll
  back to). Caveat: a migration that already committed is not reverted by the rollback.
- **Reboot / idle stop**: every compose service has `restart: unless-stopped`, and `smartsched-stack.service`
  (`gates/stack-up.sh`, after `docker.service`) runs `docker compose up -d --no-build` on the deploy checkout at
  boot, so the last good stack comes back even if its containers were stopped. It never builds, pulls or stops
  anything. With no `.env` (the first deploy never ran) it starts nothing: until one deploy succeeds the panel
  has no stack and no holding page.
- **Disk**: before every run the worker cleans up, cheapest step first, until `/` is below
  `PODCI_DISK_MAX_PERCENT` (70): workspaces, old runs (keeps 50), dangling images and build cache above
  4 GB, unused images older than 24 h, all build cache, npm/pip caches, all unused images. Images used by
  the running stack are never removed.
- **Idle stop**: every poll records a CPU sample and publishes `SmartSched/Pod` `Heartbeat` and
  `CIJobRunning`. With no CI run queued, running or finished in the last 60 min and CPU below 5 % over
  60 min, the pod stops itself (`ec2:StopInstances` on its own ARN only). The CloudWatch alarm
  `smartsched-pod-idle-stop` (CPU < 5 % for 60 min) is the backstop; the worker disables its actions
  for the duration of every job.
- **Secrets**: the GitHub token is read from SSM `/smartsched/github_token` and sent to git as an HTTP
  header through `GIT_CONFIG_*` environment variables. It never appears on a command line, in
  `.git/config` or in the workspace (`git archive`). The instance metadata hop limit is 1, so gate
  containers cannot read the instance role credentials.
- **Trust boundary**: gates execute code from the configured branches of this private repository with
  the docker group (root-equivalent on the pod). Only add branches you trust to `PODCI_BRANCHES`.

## Operating it (on the pod, via SSM Session Manager)

```bash
sudo runuser -u smartsched-ci -- env PYTHONPATH=/opt/smartsched-ci python3 -m podci runs     # last runs
sudo runuser -u smartsched-ci -- env PYTHONPATH=/opt/smartsched-ci python3 -m podci rerun 12  # queue again
sudo systemctl start smartsched-ci-worker.service      # run the queue now
journalctl -u smartsched-ci-worker -f                   # live worker log; per-gate logs: /var/lib/smartsched-ci/logs/<run>/
sudo systemctl list-timers 'smartsched-ci*'
```

The `/ci/` basic-auth credentials (`ci:<password>`):
`aws ssm get-parameter --name /smartsched/ci/basic_auth --with-decryption --query Parameter.Value --output text`.

## Tests

```bash
python -m pytest infra/aws/tests smartsched/deploy/pod-ci/tests -q
ruff check infra/aws smartsched/deploy/pod-ci
```

They cover the poller (ls-remote parsing, token handling, enqueue/supersede, statuses), the state
machine (transitions, recovery after a crash, persistence), status posting against a mock HTTP opener
(request shape, retries on 5xx, no retry on 4xx), the worker (gate order, skips, deploy gating, error
handling, the lock), the nginx rendering (`nginx -t` when nginx is installed), the `/ci/` page and its
auth, `.env` generation and disk cleanup.
