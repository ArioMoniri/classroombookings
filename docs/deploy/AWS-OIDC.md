# AWS access for SmartSched (created 2026-10-08)

Created by `.github/workflows/aws-oidc-bootstrap.yml` (run 37767920836, success) using the temporary secrets once.
Re-run it by changing `infra/aws/OIDC_BOOTSTRAP` (all steps are idempotent).

| Item | Value |
|---|---|
| AWS account | `235229001983` |
| Region | from the `AWS_DEFAULT_REGION` secret (us-east-1) |
| GitHub OIDC provider | `token.actions.githubusercontent.com` (audience `sts.amazonaws.com`) |
| Role | `arn:aws:iam::235229001983:role/smartsched-github-bootstrap` |
| Role trust | only `repo:ArioMoniri/classroombookings` on `refs/heads/claude/gracious-cerf-w1598m` and `refs/heads/claude/smartsched-universal` |
| Role permissions (inline `smartsched-github-bootstrap`) | ec2, ssm, cloudwatch, logs, budgets, pricing read, cost-explorer read on `*`; IAM only on `role/`, `instance-profile/`, `policy/` named `smartsched-*`; `iam:CreateServiceLinkedRole` |
| Budget | `smartsched-monthly-100usd`: $100 per month, e-mail alerts to umutk@getvivax.com at 50 %, 80 %, 100 % actual and 100 % forecasted |

## What you need to do

1. Add the repository secret **`AWS_ROLE_ARN`** = `arn:aws:iam::235229001983:role/smartsched-github-bootstrap`.
   From then on, workflows assume this role with `permissions: id-token: write` and the temporary keys are no longer needed.
2. Confirm the AWS Budgets subscription e-mail sent to umutk@getvivax.com (alerts start after confirmation).
3. Add **`POD_GITHUB_TOKEN`** (fine-grained, this repo only: Contents read, Commit statuses read/write, Metadata read).

AWS Budgets alerts but does not block spending by itself; the pod bootstrap adds a budget action that stops the instance at 100 %.
To remove everything later: delete the role, the OIDC provider and the budget in the AWS console (or run the pod bootstrap's `down`).

## Fix 2026-10-08: GitHub now signs the `sub` claim with immutable IDs

The first pod bootstrap failed with "Not authorized to perform sts:AssumeRoleWithWebIdentity". The workflow printed the
real claim: `repo:ArioMoniri@92126657/classroombookings@1409398656:ref:refs/heads/claude/gracious-cerf-w1598m`
(owner and repository IDs are now part of `sub`). The role's trust policy must list that form. Paste this as the role's
**Trust relationships** in the IAM console (Roles → smartsched-github-bootstrap → Trust relationships → Edit), or refresh
the temporary AWS_* secrets and push `infra/aws/OIDC_BOOTSTRAP` so the bootstrap job writes it:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::235229001983:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": [
        "repo:ArioMoniri@92126657/classroombookings@1409398656:ref:refs/heads/claude/gracious-cerf-w1598m",
        "repo:ArioMoniri@92126657/classroombookings@1409398656:ref:refs/heads/claude/smartsched-universal",
        "repo:ArioMoniri/classroombookings:ref:refs/heads/claude/gracious-cerf-w1598m",
        "repo:ArioMoniri/classroombookings:ref:refs/heads/claude/smartsched-universal"
      ]}
    }
  }]
}
```
