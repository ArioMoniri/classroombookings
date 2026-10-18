# Security policy

SmartSched holds personal data of students and staff (KVKK), so security reports get priority.

## Reporting a vulnerability

**Please do not open a public issue, discussion or pull request for a vulnerability.**

1. Open the repository's **Security** tab and choose **Report a vulnerability** (GitHub private vulnerability
   reporting). Only the maintainers see the report.
2. Describe the problem, the affected version or commit, the steps to reproduce it and the impact you expect.
   Never include real personal data; use the seeded demo accounts or made-up names.
3. You get an acknowledgement within 5 working days. We agree a fix and a disclosure date with you, and credit
   you in the advisory unless you prefer otherwise.

## Supported versions

SmartSched has no tagged releases yet. Fixes go to the default branch and to the deploy branches built from it.

## Scope

In scope: the SmartSched backend (`smartsched/backend`), the frontend (`smartsched/frontend`), the deploy files
(`smartsched/deploy`) and the AWS pod tooling (`infra/aws`). The original classroombookings PHP code at the
repository root is kept for the parity gate and the legacy import; report problems in upstream classroombookings
to its own project.

## For institutions running SmartSched

Each SmartSched instance serves its own RFC 9116 `/.well-known/security.txt`. An administrator sets the contact
in **Ayarlar › Genel › Güvenlik iletişimi** (or with `--security-contact` at deploy time). Reports about a
specific university's instance should go to that contact, not to this repository.

## How SmartSched is secured

The threat model, every control with the file that implements it and its test, row-level security, rate limits
and the open risks are in [docs/SECURITY.md](../docs/SECURITY.md).
