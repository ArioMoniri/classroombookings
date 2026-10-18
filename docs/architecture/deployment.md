# Deployment

Two ways SmartSched runs: the AWS pod (one EC2 instance that also runs its own CI) and the local one-click deploy on
any Docker host. Index: [README.md](README.md). Runbooks: [docs/deploy/AWS.md](../deploy/AWS.md),
[docs/deploy/ONE-CLICK.md](../deploy/ONE-CLICK.md).

## AWS pod: control path

```mermaid
flowchart LR
  dev(["Maintainer"]) -- "commit a line to<br/>infra/aws/POD_ACTION" --> gh["GitHub"]
  gh -- "push that changes POD_ACTION<br/>(or manual dispatch)" --> wf[".github/workflows/aws-bootstrap.yml"]
  wf -- "OIDC role, no stored keys" --> aws_cli["infra/aws/smartsched_aws.py<br/>up | status | stop | start | cost | down destroy"]

  subgraph aws["AWS account (every resource tagged Project=smartsched)"]
    iam["IAM pod role + instance profile<br/>(SSM core, CloudWatch, own parameters,<br/>stop itself only)"]
    sg["security group 80/443<br/>(22 only with --ssh-cidr)"]
    eip["Elastic IP"]
    ec2["EC2 t4g.large, Ubuntu arm64<br/>40 GB gp3 encrypted, IMDSv2 hop limit 1"]
    ssm[("SSM Parameter Store<br/>/smartsched/* : panel URL, admin password,<br/>app secrets, CI token")]
    alarm["CloudWatch alarm<br/>CPU below 5 % for 60 min → stop"]
    budget["Budget $100/month<br/>action: stop at 100 %"]
  end

  aws_cli --> iam & sg & eip & ec2 & alarm & budget
  aws_cli -- "user-data: pod-bootstrap.sh" --> ec2
  ec2 -- "writes its own secrets" --> ssm
  ec2 -- "reads tokens" --> ssm
  alarm -. "stop" .-> ec2
  budget -. "stop" .-> ec2
  admin(["Users"]) -- "HTTPS (Caddy)" --> eip --> ec2
```

`POD_ACTION` is the only workflow that runs automatically, and only when that file changes; it assumes an OIDC role
and runs the idempotent bootstrap CLI. The pod generates its secrets on first boot and stores them in SSM itself
(nothing secret travels through the workflow). Cost is capped twice: an idle alarm stops the instance and a budget
action stops it at $100 a month.

Where in the code: [`infra/aws/POD_ACTION`](../../infra/aws/POD_ACTION),
[`infra/aws/smartsched_aws.py`](../../infra/aws/smartsched_aws.py),
[`infra/aws/user-data.sh.tmpl`](../../infra/aws/user-data.sh.tmpl),
[`aws-bootstrap.yml`](../../.github/workflows/aws-bootstrap.yml),
[`pod-ci/pod-bootstrap.sh`](../../smartsched/deploy/pod-ci/pod-bootstrap.sh).

## AWS pod: CI gates → deploy → health

```mermaid
sequenceDiagram
  autonumber
  participant T as systemd timer (2 min)
  participant P as podci poll
  participant GH as GitHub
  participant Q as SQLite queue
  participant W as podci work (flock, one job)
  participant G as gates/*.sh (Docker)
  participant D as gates/deploy.sh

  T->>P: tick
  P->>GH: git ls-remote (token from SSM)
  P->>Q: new head? queue it (older queued jobs superseded)
  Q->>W: path unit wakes the worker
  loop each gate in podci/gates.py order
    W->>G: prepare, validate, backend, infra, frontend,<br/>frontend-unit-1/2, e2e-real, parity, planner, images, watchdog
    G-->>W: pass / fail / skipped (needs failed)
    W->>GH: commit status pod-ci/GATE
  end
  alt deploy branch, every blocking gate green, commit still the head
    W->>D: deploy
    D->>D: deploy.sh --update --no-pull --tls
    D->>D: GET /api/v1/health until db is true
    D-->>W: healthy or fail
  end
  W->>GH: overall status pod-ci
```

The pod is its own CI: no hosted runner, no registration. Gates run strictly one after another inside Docker with
CPU and memory caps; a gate whose prerequisite failed is reported as an error, never green. Only the configured deploy
branch is deployed, only when every blocking gate passed and the commit is still that branch's head, and a deploy
counts only after the health endpoint reports the database up. Results are also served on the panel under `/ci/`.

Where in the code: [`pod-ci/README.md`](../../smartsched/deploy/pod-ci/README.md),
[`pod-ci/podci/gates.py`](../../smartsched/deploy/pod-ci/podci/gates.py),
[`pod-ci/podci/runner.py`](../../smartsched/deploy/pod-ci/podci/runner.py),
[`pod-ci/gates/deploy.sh`](../../smartsched/deploy/pod-ci/gates/deploy.sh),
[`pod-ci/systemd/`](../../smartsched/deploy/pod-ci/systemd/).

## Local one-click deploy

```mermaid
flowchart TB
  start(["./deploy.sh [--tls] [--observability] [--legacy]<br/>[--profile empty|institution]"]) --> plan["check the deploy-time settings<br/>(refused = nothing built or changed)"]
  plan --> env{".env exists?"}
  env -- no --> gen["create .env from .env.example,<br/>replace __GENERATE__ with random secrets"]
  env -- yes --> build
  gen --> build["docker compose build<br/>(digest-pinned base images)"]
  build --> up["docker compose up -d<br/>db → backend → frontend → proxy (→ caddy)"]
  up --> mig["backend entrypoint: alembic upgrade head,<br/>seed the admin (must change password)"]
  mig --> health["wait for /api/v1/health through the proxy"]
  health --> seed{"seed profile"}
  seed -- empty --> wizard["nothing loaded:<br/>setup wizard + /onboarding"]
  seed -- institution --> imp["import the fixture workbooks once"]
  wizard & imp --> boot["write settings once (org name, AI provider, SMTP)<br/>through the panel's own validation"]
  boot --> done(["optional nightly backup,<br/>print panel URL and where the admin password is"])
```

The same script serves a laptop, a school server and the pod (the pod calls it with `--update --no-pull --tls`).
Secrets are generated on first run, never passed as flags and never committed; settings are written once through the
admin panel's own validation, so a later deploy never overwrites what an administrator changed. For development
without Docker, `scripts/dev.sh --run` starts the backend and frontend on SQLite.

Where in the code: [`deploy/deploy.sh`](../../smartsched/deploy/deploy.sh),
[`deploy/docker-compose.yml`](../../smartsched/deploy/docker-compose.yml),
[`deploy/seed/`](../../smartsched/deploy/seed/), [`deploy/README.md`](../../smartsched/deploy/README.md),
[`scripts/dev.sh`](../../scripts/dev.sh).
