# SmartSched on AWS: one pod, CI on the pod, $100/month cap

One EC2 instance (the "pod") runs the whole SmartSched stack (`smartsched/deploy`, Docker Compose,
Caddy TLS) and the project's CI (`smartsched/deploy/pod-ci`). GitHub Actions is used for one thing only:
the `aws-bootstrap` workflow, which calls AWS APIs to create, inspect, stop, start or delete the pod.
No tests or image builds run on GitHub runners.

- Bootstrap CLI: `infra/aws/smartsched_aws.py` (boto3, idempotent, every resource tagged `Project=smartsched`)
- Workflow: `.github/workflows/aws-bootstrap.yml` (push of `infra/aws/POD_ACTION`, <= 10 min)
- Pod CI: `smartsched/deploy/pod-ci/README.md`
- Account access (OIDC role, budget): `docs/deploy/AWS-OIDC.md`

## 1. What gets created

| Resource | Name | Notes |
|---|---|---|
| IAM role + instance profile | `smartsched-pod-role`, `smartsched-pod-profile` | `AmazonSSMManagedInstanceCore`, `CloudWatchAgentServerPolicy`, inline `smartsched-pod`: read `/smartsched/*`, write only `/smartsched/admin_*`, `/smartsched/app/*`, `/smartsched/ci/*`, `cloudwatch:PutMetricData` in `SmartSched/Pod`, `ec2:StopInstances` on **its own instance ARN only**, enable/disable actions of its own idle alarm |
| IAM role | `smartsched-budget-action-role` | trusted by `budgets.amazonaws.com` (same account only), AWS managed `AWSBudgetsActions_RolePolicyForResourceAdministrationWithSSM` |
| Security group | `smartsched-pod-sg` | 80/tcp + 443/tcp from anywhere (IPv4 + IPv6); 22/tcp only with `--ssh-cidr` (off by default; use SSM Session Manager) |
| Elastic IP | `smartsched-pod-eip` | stable address; panel URL `https://<a-b-c-d>.sslip.io` |
| EC2 instance | `smartsched-pod` | **t4g.large** (2 vCPU Graviton, 8 GB), Ubuntu 24.04 arm64 (SSM public AMI parameter), 40 GB gp3 encrypted root (deleted with the instance), IMDSv2 only with hop limit 1, CPU credits `standard` (no surplus-credit charges), 4 GB swap |
| CloudWatch alarm | `smartsched-pod-idle-stop` | `CPUUtilization < 5 %` for 12 x 5 min -> `arn:aws:automate:<region>:ec2:stop` |
| Budget stop action | on `smartsched-monthly-100usd` | `RUN_SSM_DOCUMENTS` / `STOP_EC2_INSTANCES` at 100 % actual, automatic |
| SSM parameters | `/smartsched/*` | see section 5 |

The budget `smartsched-monthly-100usd` already exists (created by `aws-oidc-bootstrap.yml`); `up` reuses
it, adds any missing alert, and creates it only if it is gone. `down` keeps it.

**ARM64 check** (why t4g.large and not t3.large): ortools 9.15 ships `manylinux_2_28_aarch64` cp312
wheels; psycopg-binary, argon2-cffi-bindings, cryptography and uvloop ship aarch64 wheels; the
Playwright image `mcr.microsoft.com/playwright:v1.56.1-noble` (the version in `package-lock.json`) is
published for linux/amd64 and linux/arm64, and Playwright's bundled Chromium runs on arm64 Linux. The
other base images (python slim, node alpine, postgres, nginx-unprivileged, caddy, mysql, php) are
official multi-arch images. Use `--instance-type t3.large` (x86) if a dependency ever lacks arm64.

### Region and price

Default region: **us-east-1** (the account's `AWS_DEFAULT_REGION`). `up`, `status` and `cost` print the
on-demand Linux price of t4g.large and t3.large in us-east-1, eu-central-1 (Frankfurt) and eu-south-1
(Milan), read from the AWS Pricing API at run time. `--region auto` (or `region=auto` in POD_ACTION
for `status`) picks the cheaper of the two EU regions nearest Türkiye. Fallback list prices (used only
when the Pricing API cannot be reached; the output says which source was used):

| Region | t4g.large $/h | t3.large $/h |
|---|---|---|
| us-east-1 | 0.0672 | 0.0832 |
| eu-central-1 | 0.0768 | 0.0960 |
| eu-south-1 | ~0.080 | ~0.091 |

### Monthly cost estimate (us-east-1, 730 h)

| Item | Running 24/7 | Stopped all month |
|---|---|---|
| t4g.large on-demand | $49.06 | $0 |
| 40 GB gp3 | $3.20 | $3.20 |
| public IPv4 (Elastic IP) | $3.65 | $3.65 |
| CloudWatch: 1 alarm + 2 custom metrics | $0.70 | $0.70 |
| SSM Parameter Store (standard), Budgets (first 2 action budgets) | $0 | $0 |
| **Total** | **~$56.6** | **~$7.6** |

Data transfer out is covered by the 100 GB/month free allowance for a planning office. With the idle
stop, a pod used 10 h on working days (~220 h) costs roughly $22/month. `status` prints the estimate for the
current state and for 24/7 running.

## 2. How the $100 cap works

AWS Budgets **alerts; it does not cap spending by itself**. The cap is the budget **action**:

1. E-mails to umutk@getvivax.com at 50 %, 80 % and 100 % of actual spend and at 100 % of forecasted
   spend (AWS first sends a subscription confirmation e-mail: confirm it).
2. At 100 % actual, the budget action runs the SSM `STOP_EC2_INSTANCES` document for the pod
   (automatic approval, role `smartsched-budget-action-role`). The pod's compute stops costing money;
   EBS and the IPv4 address keep costing about $7/month, so the month can still end slightly above $100.
3. Budgets refreshes spend data up to three times a day, so the stop can lag spend by several hours.
   At ~$0.07/h that is cents, not dollars.
4. The action fires once per budget period. If you start the pod again after it fired, you accept
   further spend for that month (the idle stop still applies). It re-arms at the start of the next month.

Independently, the pod stops itself when idle: no CI job queued, running or finished in the last 60 min
and CPU below 5 % over 60 min (pod side, using `ec2:StopInstances` on itself), with the CloudWatch alarm
on CPU as a backstop. Pod CI disables the alarm's actions while a job runs, so a stop never interrupts
a CI job. Using the panel lightly does not count as activity: the pod may stop under an idle user; start
it again (section 6).

## 3. Running the bootstrap

`workflow_dispatch` only works for workflows on the default branch, so the workflow is triggered by a
push that changes `infra/aws/POD_ACTION`. The first line is the command:

```bash
echo "up $(date -u +%FT%TZ)" > infra/aws/POD_ACTION      # timestamp = always a change
git add infra/aws/POD_ACTION && git commit -m "pod: up" && git push
```

| First line | Effect |
|---|---|
| `up` | preflight, store `POD_GITHUB_TOKEN` in SSM, create/update everything, print the panel URL |
| `status` | inventory, alarm and budget state, orphan check (unattached volumes, idle EIPs), estimated cost |
| `stop` / `start` | stop / start the instance (data kept) |
| `cost` | month-to-date spend from Cost Explorer (account, and tagged once the `Project` cost-allocation tag is activated) + budget + estimate |
| `down destroy` | delete everything tagged `Project=smartsched` in us-east-1, eu-central-1 and eu-south-1, plus the two `smartsched-*` IAM roles; keeps the budget |

Append `region=<aws-region>` to override the region. Every run first calls `sts:GetCallerIdentity` and
fails in seconds with "credentials are EXPIRED" or "AWS rejected the credentials" when they are bad;
nothing is half-created that a re-run would not finish (find-or-create everywhere, including after
renewing temporary keys). `up` takes ~3-5 minutes in Actions. The pod then needs ~15-25 more minutes on
its own (Docker install, first image builds, Let's Encrypt) before the panel answers.

The job summary lists the panel URL, instance id, admin e-mail, the command to read the admin password
and the SSM parameter **names**. Secret values are never printed.

Local equivalent (any machine with credentials): `python infra/aws/smartsched_aws.py up|status|stop|start|cost|down --yes`.
Offline, no AWS calls: `python infra/aws/smartsched_aws.py plan` and `... render-user-data`.

## 4. What the user must provide

1. **AWS credentials for the workflow**, either
   - **(preferred, in place)** the repository secret `AWS_ROLE_ARN` =
     `arn:aws:iam::235229001983:role/smartsched-github-bootstrap` (GitHub OIDC, no stored keys), or
   - temporary keys in `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, valid for at
     least **30 minutes** after the push.
2. **`POD_GITHUB_TOKEN`** repository secret: fine-grained personal access token, repository access =
   only `ArioMoniri/classroombookings`, permissions **Contents: Read**, **Commit statuses: Read and
   write**, **Metadata: Read**. The pod uses it for `git ls-remote`/`fetch` and to post statuses.
3. Confirm the AWS Budgets subscription e-mail at umutk@getvivax.com.
4. Optional: `AWS_REGION` / `AWS_DEFAULT_REGION` secret (default us-east-1).

### GitHub OIDC (how the existing role was set up; to recreate or tighten it)

Identity provider (IAM console > Identity providers > Add > OpenID Connect): URL
`https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.

**Trust policy, strict** (only `aws-bootstrap.yml` on `claude/gracious-cerf-w1598m`; file `infra/aws/iam/github-oidc-trust-policy.json`). GitHub's default
`sub` claim does not contain the workflow file, so first make the repository include it (this changes
the `sub` of every workflow in the repo; update every role trusting this repo at the same time):

```bash
gh api -X PUT repos/ArioMoniri/classroombookings/actions/oidc/customization/sub \
  -F use_default=false -f 'include_claim_keys[]=repo' -f 'include_claim_keys[]=context' \
  -f 'include_claim_keys[]=job_workflow_ref'
```

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::235229001983:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:ArioMoniri/classroombookings:ref:refs/heads/claude/gracious-cerf-w1598m:job_workflow_ref:ArioMoniri/classroombookings/.github/workflows/aws-bootstrap.yml@refs/heads/claude/gracious-cerf-w1598m"
      }
    }
  }]
}
```

**Trust policy, branch only** (default `sub`; what `smartsched-github-bootstrap` uses today, plus the
`claude/smartsched-universal` branch): condition
`"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com", "token.actions.githubusercontent.com:sub": "repo:ArioMoniri/classroombookings:ref:refs/heads/claude/gracious-cerf-w1598m"}`.
Any workflow on that branch can then assume the role.

**Minimal permission policy** for the bootstrap identity: `infra/aws/iam/bootstrap-policy.json`
(reproduced below). Read-only discovery on `*`; EC2 creation on `*`; every destructive EC2 call only on
resources tagged `Project=smartsched`; IAM only on `role/smartsched-*` and `instance-profile/smartsched-*`
(PassRole only to EC2 and Budgets); SSM only under `/smartsched` plus the public Ubuntu AMI parameters;
alarms and budgets only named `smartsched-*`. A unit test records every API call `up` and `down` make
(botocore Stubber) and checks it against this file and against the existing role's broader policy.
The existing role lacks `tag:GetResources`; `down` then reports the leftover check as "not checked".

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "ReadOnlyDiscovery", "Effect": "Allow", "Resource": "*", "Action": [
      "ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeInstanceTypeOfferings", "ec2:DescribeImages",
      "ec2:DescribeInstances", "ec2:DescribeSecurityGroups", "ec2:DescribeAddresses", "ec2:DescribeVolumes",
      "cloudwatch:DescribeAlarms", "pricing:GetProducts", "ce:GetCostAndUsage", "tag:GetResources",
      "ssm:DescribeParameters"]},
    {"Sid": "CreateTaggedEc2", "Effect": "Allow", "Resource": "*", "Action": [
      "ec2:RunInstances", "ec2:CreateSecurityGroup", "ec2:AllocateAddress", "ec2:AssociateAddress",
      "ec2:DisassociateAddress", "ec2:CreateTags"]},
    {"Sid": "MutateOnlyProjectTagged", "Effect": "Allow", "Resource": "*",
     "Condition": {"StringEquals": {"aws:ResourceTag/Project": "smartsched"}}, "Action": [
      "ec2:StartInstances", "ec2:StopInstances", "ec2:TerminateInstances", "ec2:AuthorizeSecurityGroupIngress",
      "ec2:RevokeSecurityGroupIngress", "ec2:DeleteSecurityGroup", "ec2:ReleaseAddress", "ec2:DeleteVolume"]},
    {"Sid": "UbuntuAmiLookup", "Effect": "Allow", "Action": "ssm:GetParameter",
     "Resource": "arn:aws:ssm:*::parameter/aws/service/canonical/*"},
    {"Sid": "OwnParameters", "Effect": "Allow",
     "Resource": ["arn:aws:ssm:*:*:parameter/smartsched", "arn:aws:ssm:*:*:parameter/smartsched/*"], "Action": [
      "ssm:PutParameter", "ssm:GetParameter", "ssm:GetParametersByPath", "ssm:DeleteParameter",
      "ssm:DeleteParameters", "ssm:AddTagsToResource"]},
    {"Sid": "IdleAlarm", "Effect": "Allow", "Resource": "arn:aws:cloudwatch:*:*:alarm:smartsched-*",
     "Action": ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource"]},
    {"Sid": "AlarmEc2ActionServiceLinkedRole", "Effect": "Allow", "Action": "iam:CreateServiceLinkedRole",
     "Resource": "arn:aws:iam::*:role/aws-service-role/events.amazonaws.com/AWSServiceRoleForCloudWatchEvents*",
     "Condition": {"StringLike": {"iam:AWSServiceName": "events.amazonaws.com"}}},
    {"Sid": "OwnRolesAndProfile", "Effect": "Allow",
     "Resource": ["arn:aws:iam::*:role/smartsched-*", "arn:aws:iam::*:instance-profile/smartsched-*"], "Action": [
      "iam:GetRole", "iam:CreateRole", "iam:DeleteRole", "iam:TagRole", "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:ListRolePolicies", "iam:AttachRolePolicy",
      "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies", "iam:GetInstanceProfile",
      "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:TagInstanceProfile",
      "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile"]},
    {"Sid": "PassOwnRoles", "Effect": "Allow", "Action": "iam:PassRole", "Resource": "arn:aws:iam::*:role/smartsched-*",
     "Condition": {"StringEquals": {"iam:PassedToService": ["ec2.amazonaws.com", "budgets.amazonaws.com"]}}},
    {"Sid": "MonthlyBudgetAndStopAction", "Effect": "Allow",
     "Resource": ["arn:aws:budgets::*:budget/smartsched-*", "arn:aws:budgets::*:budget/smartsched-*/action/*"],
     "Action": ["budgets:ViewBudget", "budgets:ModifyBudget", "budgets:CreateBudgetAction",
      "budgets:UpdateBudgetAction", "budgets:DeleteBudgetAction", "budgets:DescribeBudgetAction",
      "budgets:DescribeBudgetActionsForBudget", "budgets:TagResource", "budgets:ListTagsForResource"]}
  ]
}
```

## 5. Reaching the panel and the admin credentials

- Panel: `https://<a-b-c-d>.sslip.io` (the Elastic IP with dashes; sslip.io resolves it to the IP, and
  Caddy gets a Let's Encrypt certificate for that name). HTTPS is required: the session cookie is
  `Secure`. Also stored in SSM `/smartsched/panel_url`.
- Admin e-mail: `umutk@getvivax.com` (`--admin-email` to change; SSM `/smartsched/admin_email`).
- Admin password, generated on the pod at first boot and never leaving AWS except when you read it:

```bash
aws ssm get-parameter --region us-east-1 --name /smartsched/admin_password --with-decryption \
  --query Parameter.Value --output text
```

| SSM parameter | Type | Written by |
|---|---|---|
| `/smartsched/panel_url` | String | `up` |
| `/smartsched/github_token` | SecureString | workflow (`POD_GITHUB_TOKEN`) |
| `/smartsched/admin_email`, `/smartsched/admin_password` | String, SecureString | pod |
| `/smartsched/app/APP_SECRET`, `JWT_SECRET`, `AUTH_SECRET`, `POSTGRES_PASSWORD` | SecureString | pod (backup of `deploy/.env`) |
| `/smartsched/ci/basic_auth` | SecureString | pod (`ci:<password>` for `/ci/`) |

The password is seeded once; change it in the UI after the first login (SSM keeps the initial value).

- CI results: `https://<panel>/ci/` (log in to SmartSched as an admin first, or use the basic-auth pair).
- Shell on the pod without SSH: `aws ssm start-session --target <instance-id>` (Session Manager plugin).
  First-boot log: `/var/log/smartsched-bootstrap.log`; stack: `/opt/smartsched/src/smartsched/deploy`.

## 6. Stop, start, destroy

- **Stop** (`stop`): compute billing stops; disk, data and the IP stay (~$7.6/month).
- **Start** (`start`): same IP and URL; containers restart on their own (`restart: unless-stopped`), pod
  CI resumes polling and catches up with any commits pushed while it was stopped.
- **Destroy** (`down destroy`): terminates the instance (its disk and ALL data go with it; back up
  first, `smartsched/deploy/README.md` "Backups"), releases the EIP, deletes volumes, the security group,
  the alarm, the budget action, `/smartsched/*` parameters (including the GitHub token) and the
  `smartsched-pod-*`/`smartsched-budget-action-role` IAM resources. It keeps the budget and the OIDC role
  (`smartsched-github-bootstrap`). `--keep-parameters` / `--delete-budget` adjust that when run locally.
- **Waste control**: `up` releases tagged EIPs that are not attached; the root volume is deleted with the
  instance; `status` lists any unattached tagged volume or idle EIP under `orphans`; `down` checks the
  Resource Groups Tagging API for anything left.

## 7. Scaling beyond one pod

The pod is sized for one planning office (README "Sizing"). In order:

1. **Bigger instance**: `down` is not needed for a resize: stop, change the type in the console
   (t4g.xlarge, m7g.large), start. Raise `BACKEND_CPUS`/`SOLVER_WORKERS` in `deploy/.env`.
2. **Managed Postgres** (RDS): set `DATABASE_URL`, drop the `db` service; then the pod is stateless
   except uploads (move them to S3 or EFS).
3. **Several app instances** behind an ALB, each running the compose stack with `RUN_MIGRATIONS=0`
   except one; CI stays on a single pod. Solver jobs need the planned Redis queue first
   (`smartsched/deploy/README.md` "Scaling").

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| workflow fails at preflight | credentials expired/invalid: renew the secrets or set `AWS_ROLE_ARN`; push POD_ACTION again |
| panel not reachable 30 min after `up` | `aws ssm start-session`, `tail -f /var/log/smartsched-bootstrap.log`; "waiting for SSM /smartsched/github_token" = `POD_GITHUB_TOKEN` missing |
| certificate errors | Let's Encrypt rate limits for `sslip.io` names: point your own DNS name at the EIP, set `TLS_DOMAIN`, `PUBLIC_URL`, `CORS_ORIGINS` in `deploy/.env`, `./deploy.sh --update --tls` |
| no ✓/✗ on commits | token lacks Commit statuses: write, or the pod is stopped (idle/budget); `start` it |
| pod stopped by itself | idle stop or the budget action; see the alarm history / budget e-mails; `start` |
