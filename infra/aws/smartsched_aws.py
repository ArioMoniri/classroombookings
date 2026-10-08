#!/usr/bin/env python3
"""SmartSched AWS pod: idempotent bootstrap CLI (boto3).

    python infra/aws/smartsched_aws.py up       [--region R|auto] [--instance-type T] [--ssh-cidr CIDR] ...
    python infra/aws/smartsched_aws.py status   # inventory, alarm/budget state, orphan check, est. monthly cost
    python infra/aws/smartsched_aws.py stop | start
    python infra/aws/smartsched_aws.py down --yes   # delete everything tagged Project=smartsched (the
                                                    # budget is kept unless --delete-budget)
    python infra/aws/smartsched_aws.py cost     # month-to-date spend (Cost Explorer) + budget + estimate
    python infra/aws/smartsched_aws.py plan     # OFFLINE: what `up` creates + rendered user-data, no AWS calls
    python infra/aws/smartsched_aws.py preflight            # sts get-caller-identity with a clear error
    python infra/aws/smartsched_aws.py put-github-token --from-env POD_GITHUB_TOKEN

What `up` creates (every resource tagged Project=smartsched; see docs/deploy/AWS.md):
  IAM   smartsched-pod-role + smartsched-pod-profile (SSM core, CloudWatch agent, own /smartsched/*
        parameters, ec2:StopInstances + alarm enable/disable on ITSELF only), smartsched-budget-action-role
  EC2   security group (80/443, optional 22 from --ssh-cidr), Elastic IP, one t4g.large (Ubuntu 24.04
        arm64, 40 GB gp3 encrypted, IMDSv2 hop limit 1 so CI containers cannot read role credentials)
  CW    alarm smartsched-pod-idle-stop: CPU < 5 % for 60 min -> stop (pod CI disables the alarm's
        actions while a job runs and publishes Heartbeat/CIJobRunning metrics)
  Budget smartsched-monthly-100usd (already created by aws-oidc-bootstrap.yml; reused, created only if
        missing): $100/month, e-mail at 50/80/100 % actual + 100 % forecast, plus a budget action that
        stops the instance at 100 % actual (AWS Budgets alerts; the stop action is the cap)
  SSM   /smartsched/panel_url (+ the pod writes /smartsched/admin_* and /smartsched/app/* itself)

ARM64: ortools publishes manylinux aarch64 cp312 wheels (9.15.x), psycopg-binary/argon2/cryptography/
uvloop ship aarch64 wheels, and Playwright's mcr.microsoft.com/playwright:v1.56.1-noble image and
bundled Chromium support linux/arm64, so t4g.large is the default; --instance-type t3.large is the
x86 fallback.

Credentials: standard AWS env/profile (temporary STS keys with AWS_SESSION_TOKEN work). Every command
except `plan` first calls sts:GetCallerIdentity and exits 2 with a clear message when the keys are
expired or invalid. Re-running `up` after renewing credentials is safe (find-or-create everywhere).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

HERE = Path(__file__).resolve().parent

PROJECT = "smartsched"
TAG_KEY, TAG_VALUE = "Project", PROJECT
INSTANCE_NAME = "smartsched-pod"
SG_NAME = "smartsched-pod-sg"
EIP_NAME = "smartsched-pod-eip"
ROLE_NAME = "smartsched-pod-role"
PROFILE_NAME = "smartsched-pod-profile"
POD_POLICY_NAME = "smartsched-pod"
BUDGET_ROLE_NAME = "smartsched-budget-action-role"
# Created once by .github/workflows/aws-oidc-bootstrap.yml (docs/deploy/AWS-OIDC.md); `up` reuses it,
# adds any missing alert and the stop action, and only creates it when it does not exist at all.
BUDGET_NAME = "smartsched-monthly-100usd"
ALARM_NAME = "smartsched-pod-idle-stop"
SSM_PREFIX = "/smartsched"
HEARTBEAT_NAMESPACE = "SmartSched/Pod"

DEFAULT_REGION = "us-east-1"  # the user's AWS_DEFAULT_REGION; --region auto picks the cheaper EU region
NEAR_TURKIYE = ("eu-central-1", "eu-south-1")
PRICE_REGIONS = ("us-east-1", "eu-central-1", "eu-south-1")
COMPARE_TYPES = ("t4g.large", "t3.large")
DEFAULT_EMAIL = "umutk@getvivax.com"
DEFAULT_REPO = "ArioMoniri/classroombookings"
DEFAULT_DEPLOY_BRANCH = "claude/gracious-cerf-w1598m"
DEFAULT_CI_BRANCHES = ("claude/gracious-cerf-w1598m", "claude/smartsched-universal")
BUDGET_ALERTS = (("ACTUAL", 50.0), ("ACTUAL", 80.0), ("ACTUAL", 100.0), ("FORECASTED", 100.0))
GLOBAL_REGION = "us-east-1"  # IAM, Budgets, Cost Explorer and the Pricing API endpoint

POD_MANAGED_POLICIES = (
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
)
# AWS-managed policy documented for budget actions that run SSM stop/start documents.
BUDGET_ACTION_MANAGED_POLICY = "arn:aws:iam::aws:policy/AWSBudgetsActions_RolePolicyForResourceAdministrationWithSSM"

REGION_NAMES = {"us-east-1": "US East (N. Virginia)", "eu-central-1": "EU (Frankfurt)", "eu-south-1": "EU (Milan)"}
# Fallback list prices (USD), used only when the Pricing API cannot be reached; `up`/`status` say so.
FALLBACK_HOURLY = {
    ("us-east-1", "t4g.large"): 0.0672,
    ("us-east-1", "t3.large"): 0.0832,
    ("eu-central-1", "t4g.large"): 0.0768,
    ("eu-central-1", "t3.large"): 0.0960,
    ("eu-south-1", "t4g.large"): 0.0800,
    ("eu-south-1", "t3.large"): 0.0912,
}
FALLBACK_GP3_GB_MONTH = {"us-east-1": 0.08, "eu-central-1": 0.0952, "eu-south-1": 0.0924}
PUBLIC_IPV4_HOURLY = 0.005  # every public IPv4 (EIP attached or idle) since 2024-02
CW_ALARM_MONTHLY = 0.10
CW_CUSTOM_METRIC_MONTHLY = 0.30
POD_CUSTOM_METRICS = 2  # Heartbeat, CIJobRunning
HOURS_PER_MONTH = 730

EXPIRED_CODES = {"ExpiredToken", "ExpiredTokenException", "RequestExpired"}
INVALID_CODES = {"InvalidClientTokenId", "UnrecognizedClientException", "SignatureDoesNotMatch", "AuthFailure"}


class BootstrapError(Exception):
    """A failure with an operator-facing message (printed without a traceback)."""


# ------------------------------------------------------------------------------------------------
# small helpers
# ------------------------------------------------------------------------------------------------
def tags(name: str | None = None, extra: dict[str, str] | None = None) -> list[dict[str, str]]:
    out = [{"Key": TAG_KEY, "Value": TAG_VALUE}, {"Key": "ManagedBy", "Value": "infra/aws/smartsched_aws.py"}]
    if name:
        out.append({"Key": "Name", "Value": name})
    for k, v in (extra or {}).items():
        out.append({"Key": k, "Value": v})
    return out


def tag_filter(name: str | None = None) -> list[dict[str, Any]]:
    f: list[dict[str, Any]] = [{"Name": f"tag:{TAG_KEY}", "Values": [TAG_VALUE]}]
    if name:
        f.append({"Name": "tag:Name", "Values": [name]})
    return f


def error_code(exc: BaseException) -> str:
    resp = getattr(exc, "response", None) or {}
    return str(resp.get("Error", {}).get("Code", ""))


def arch_for(instance_type: str) -> str:
    """Graviton families carry a 'g' after the generation digit: t4g, m7gd, c6gn (a1 is the first Graviton)."""
    family = instance_type.split(".", 1)[0]
    return "arm64" if family == "a1" or re.match(r"^[a-z]+\d+[a-z]*g", family) else "amd64"


def panel_domain(public_ip: str) -> str:
    """Free wildcard DNS: 1-2-3-4.sslip.io -> 1.2.3.4, so Caddy can get a Let's Encrypt certificate."""
    return public_ip.replace(".", "-") + ".sslip.io"


def log(msg: str) -> None:
    print(f"[smartsched-aws] {msg}", file=sys.stderr, flush=True)


def wait_for(check: Callable[[], bool], what: str, timeout: float = 600, interval: float = 5,
             sleep: Callable[[float], None] = time.sleep) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if check():
            return
        if time.monotonic() > deadline:
            raise BootstrapError(f"timed out after {int(timeout)} s waiting for {what}")
        sleep(interval)


@dataclass
class Settings:
    region: str = DEFAULT_REGION
    instance_type: str = "t4g.large"
    volume_gb: int = 40
    ssh_cidr: str | None = None
    budget_usd: float = 100.0
    alert_email: str = DEFAULT_EMAIL
    admin_email: str = DEFAULT_EMAIL
    acme_email: str = DEFAULT_EMAIL
    repo: str = DEFAULT_REPO
    deploy_branch: str = DEFAULT_DEPLOY_BRANCH
    ci_branches: tuple[str, ...] = DEFAULT_CI_BRANCHES
    cpu_credits: str = "standard"
    idle_minutes: int = 60
    idle_cpu_percent: float = 5.0
    docker_version: str = ""
    budget_action: bool = True


# ------------------------------------------------------------------------------------------------
# client access (tests inject stubbed clients)
# ------------------------------------------------------------------------------------------------
class Aws:
    GLOBAL_SERVICES: ClassVar[frozenset[str]] = frozenset({"iam", "budgets", "ce", "pricing"})

    def __init__(self, region: str, session: Any = None, clients: dict[tuple[str, str], Any] | None = None):
        self.region = region
        self._session = session
        self._clients: dict[tuple[str, str], Any] = dict(clients or {})

    def client(self, service: str, region: str | None = None) -> Any:
        reg = GLOBAL_REGION if service in self.GLOBAL_SERVICES else (region or self.region)
        key = (service, reg)
        if key not in self._clients:
            if self._session is None:
                import boto3  # imported lazily so `plan` and the tests' helpers work without network

                self._session = boto3.session.Session()
            from botocore.config import Config

            self._clients[key] = self._session.client(service, region_name=reg,
                                                      config=Config(retries={"max_attempts": 8, "mode": "adaptive"}))
        return self._clients[key]


# ------------------------------------------------------------------------------------------------
# preflight
# ------------------------------------------------------------------------------------------------
def credential_expiry_warning(env: dict[str, str] | None = None, now: dt.datetime | None = None) -> str | None:
    """AWS_CREDENTIAL_EXPIRATION (set by some STS tooling): fail when past, warn when < 30 min left."""
    env = os.environ if env is None else env
    raw = env.get("AWS_CREDENTIAL_EXPIRATION", "").strip()
    if not raw:
        return None
    try:
        exp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return f"AWS_CREDENTIAL_EXPIRATION={raw!r} is not an ISO timestamp; ignoring it"
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.UTC)
    now = now or dt.datetime.now(dt.UTC)
    left = (exp - now).total_seconds()
    if left <= 0:
        raise BootstrapError(
            f"the AWS credentials expired at {exp.isoformat()} (AWS_CREDENTIAL_EXPIRATION). Renew the "
            "temporary keys in the GitHub secrets (or configure the AWS_ROLE_ARN OIDC role) and re-run; "
            "`up` is safe to re-run."
        )
    if left < 1800:
        return f"the AWS credentials expire in {int(left // 60)} min; `up` needs ~10 min of API calls"
    return None


def preflight(aws: Aws) -> dict[str, str]:
    from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

    warn = credential_expiry_warning()
    if warn:
        log(f"warning: {warn}")
    try:
        ident = aws.client("sts").get_caller_identity()
    except (NoCredentialsError, PartialCredentialsError) as exc:
        raise BootstrapError(
            "no AWS credentials found. Set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY (+ AWS_SESSION_TOKEN for "
            "temporary keys) or use the OIDC role (docs/deploy/AWS.md)."
        ) from exc
    except ClientError as exc:
        code = error_code(exc)
        if code in EXPIRED_CODES:
            raise BootstrapError(
                f"the AWS credentials are EXPIRED ({code}). Put fresh temporary keys into the GitHub secrets "
                "(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN) or set AWS_ROLE_ARN for OIDC, "
                "then re-run the workflow; nothing is left half-created that a re-run does not finish."
            ) from exc
        if code in INVALID_CODES:
            raise BootstrapError(
                f"AWS rejected the credentials ({code}): the access key id / secret / session token do not "
                "match a valid identity (placeholder values, a typo, or a missing AWS_SESSION_TOKEN for "
                "ASIA... keys)."
            ) from exc
        raise BootstrapError(f"sts:GetCallerIdentity failed: {code}: {exc}") from exc
    return {"account": ident["Account"], "arn": ident["Arn"]}


# ------------------------------------------------------------------------------------------------
# pricing and region choice
# ------------------------------------------------------------------------------------------------
def _ondemand_usd(price_item: str) -> float | None:
    doc = json.loads(price_item)
    for term in doc.get("terms", {}).get("OnDemand", {}).values():
        for dim in term.get("priceDimensions", {}).values():
            usd = dim.get("pricePerUnit", {}).get("USD")
            if usd is not None and float(usd) > 0:
                return float(usd)
    return None


def ec2_hourly_price(aws: Aws, region: str, instance_type: str) -> tuple[float, str]:
    """On-demand Linux price per hour from the Pricing API; falls back to the static table."""
    try:
        resp = aws.client("pricing").get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                {"Type": "TERM_MATCH", "Field": "licenseModel", "Value": "No License required"},
            ],
            MaxResults=10,
        )
        for item in resp.get("PriceList", []):
            usd = _ondemand_usd(item)
            if usd:
                return usd, "pricing-api"
    except Exception as exc:  # noqa: BLE001 - any failure falls back to the documented table
        log(f"pricing API unavailable for {instance_type} in {region} ({error_code(exc) or exc}); using list price")
    fallback = FALLBACK_HOURLY.get((region, instance_type))
    if fallback is None:
        raise BootstrapError(f"no price known for {instance_type} in {region}")
    return fallback, "fallback-table"


def gp3_price(aws: Aws, region: str) -> tuple[float, str]:
    try:
        resp = aws.client("pricing").get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
                {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": "gp3"},
                {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
            ],
            MaxResults=10,
        )
        for item in resp.get("PriceList", []):
            usd = _ondemand_usd(item)
            if usd:
                return usd, "pricing-api"
    except Exception as exc:  # noqa: BLE001
        log(f"pricing API unavailable for gp3 in {region} ({error_code(exc) or exc}); using list price")
    return FALLBACK_GP3_GB_MONTH.get(region, 0.08), "fallback-table"


def price_table(aws: Aws, regions: Iterable[str] = PRICE_REGIONS,
                types: Iterable[str] = COMPARE_TYPES) -> dict[tuple[str, str], tuple[float, str]]:
    return {(r, t): ec2_hourly_price(aws, r, t) for r in regions for t in types}


def choose_region(prices: dict[tuple[str, str], tuple[float, str]], instance_type: str,
                  candidates: Iterable[str] = NEAR_TURKIYE) -> str:
    """Cheapest candidate region for the instance type (ties keep the candidate order)."""
    best: tuple[float, str] | None = None
    for region in candidates:
        if (region, instance_type) not in prices:
            continue
        p = prices[(region, instance_type)][0]
        if best is None or p < best[0]:
            best = (p, region)
    if best is None:
        raise BootstrapError(f"no price for {instance_type} in {list(candidates)}")
    return best[1]


def format_price_table(prices: dict[tuple[str, str], tuple[float, str]]) -> str:
    lines = ["region         type        USD/h    USD/month (730 h)  source"]
    for (region, itype), (p, src) in sorted(prices.items()):
        lines.append(f"{region:<14} {itype:<10} {p:>7.4f}  {p * HOURS_PER_MONTH:>10.2f}          {src}")
    return "\n".join(lines)


def estimate_monthly(hourly: float, gp3_gb_month: float, volume_gb: int, running: bool = True,
                     eips: int = 1, alarms: int = 1) -> dict[str, float]:
    compute = hourly * HOURS_PER_MONTH if running else 0.0
    est = {
        "compute": round(compute, 2),
        "ebs_gp3": round(gp3_gb_month * volume_gb, 2),
        "public_ipv4": round(PUBLIC_IPV4_HOURLY * HOURS_PER_MONTH * eips, 2),
        "cloudwatch": round(CW_ALARM_MONTHLY * alarms + CW_CUSTOM_METRIC_MONTHLY * POD_CUSTOM_METRICS, 2),
        "ssm_parameters": 0.0,  # standard tier is free
        "budgets": 0.0,  # the first two action-enabled budgets are free
    }
    est["total"] = round(sum(est.values()), 2)
    return est


# ------------------------------------------------------------------------------------------------
# IAM
# ------------------------------------------------------------------------------------------------
def ec2_trust_policy() -> dict[str, Any]:
    return {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]}


def budgets_trust_policy(account: str) -> dict[str, Any]:
    return {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "budgets.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": account}}}]}


def pod_role_policy(account: str, region: str, instance_id: str | None) -> dict[str, Any]:
    """Inline policy of the pod role. Stop/alarm rights name the instance and its alarm explicitly."""
    param = f"arn:aws:ssm:{region}:{account}:parameter{SSM_PREFIX}"
    statements: list[dict[str, Any]] = [
        {"Sid": "ReadOwnParameters", "Effect": "Allow",
         "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
         "Resource": [param, f"{param}/*"]},
        # The pod generates the admin password and app secrets itself and stores them here.
        {"Sid": "WriteGeneratedSecrets", "Effect": "Allow",
         "Action": ["ssm:PutParameter", "ssm:AddTagsToResource"],
         "Resource": [f"{param}/admin_email", f"{param}/admin_password", f"{param}/app/*", f"{param}/ci/*"]},
        {"Sid": "Heartbeat", "Effect": "Allow", "Action": "cloudwatch:PutMetricData", "Resource": "*",
         "Condition": {"StringEquals": {"cloudwatch:namespace": HEARTBEAT_NAMESPACE}}},
    ]
    if instance_id:
        statements.append({"Sid": "StopSelfOnly", "Effect": "Allow", "Action": "ec2:StopInstances",
                           "Resource": f"arn:aws:ec2:{region}:{account}:instance/{instance_id}"})
    statements.append({"Sid": "IdleAlarmToggle", "Effect": "Allow",
                       "Action": ["cloudwatch:DisableAlarmActions", "cloudwatch:EnableAlarmActions"],
                       "Resource": f"arn:aws:cloudwatch:{region}:{account}:alarm:{ALARM_NAME}"})
    return {"Version": "2012-10-17", "Statement": statements}


def _ensure_role(iam: Any, name: str, trust: dict[str, Any], description: str) -> str:
    try:
        role = iam.get_role(RoleName=name)["Role"]
        iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
        log(f"IAM role {name} exists")
        return str(role["Arn"])
    except Exception as exc:
        if error_code(exc) != "NoSuchEntity":
            raise
    role = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Description=description,
                           Tags=tags(name), MaxSessionDuration=3600)["Role"]
    log(f"IAM role {name} created")
    return str(role["Arn"])


def _attach_managed(iam: Any, role: str, arns: Iterable[str]) -> None:
    have = {p["PolicyArn"] for p in iam.list_attached_role_policies(RoleName=role)["AttachedPolicies"]}
    for arn in arns:
        if arn not in have:
            iam.attach_role_policy(RoleName=role, PolicyArn=arn)


def ensure_pod_role(aws: Aws, account: str, region: str, instance_id: str | None = None) -> str:
    iam = aws.client("iam")
    _ensure_role(iam, ROLE_NAME, ec2_trust_policy(), "SmartSched pod (SSM, CloudWatch, own parameters, self-stop)")
    _attach_managed(iam, ROLE_NAME, POD_MANAGED_POLICIES)
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName=POD_POLICY_NAME,
                        PolicyDocument=json.dumps(pod_role_policy(account, region, instance_id)))
    try:
        profile = iam.get_instance_profile(InstanceProfileName=PROFILE_NAME)["InstanceProfile"]
    except Exception as exc:
        if error_code(exc) != "NoSuchEntity":
            raise
        profile = iam.create_instance_profile(InstanceProfileName=PROFILE_NAME,
                                              Tags=tags(PROFILE_NAME))["InstanceProfile"]
        log(f"instance profile {PROFILE_NAME} created")
    if not any(r["RoleName"] == ROLE_NAME for r in profile.get("Roles", [])):
        iam.add_role_to_instance_profile(InstanceProfileName=PROFILE_NAME, RoleName=ROLE_NAME)
    return str(profile["Arn"])


def ensure_budget_role(aws: Aws, account: str) -> str:
    iam = aws.client("iam")
    arn = _ensure_role(iam, BUDGET_ROLE_NAME, budgets_trust_policy(account),
                       "AWS Budgets action: stop the SmartSched pod at 100 % of the monthly budget")
    _attach_managed(iam, BUDGET_ROLE_NAME, [BUDGET_ACTION_MANAGED_POLICY])
    return arn


# ------------------------------------------------------------------------------------------------
# network
# ------------------------------------------------------------------------------------------------
def default_subnet(aws: Aws, instance_type: str) -> tuple[str, str]:
    ec2 = aws.client("ec2")
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise BootstrapError(f"no default VPC in {aws.region}; create one with `aws ec2 create-default-vpc` "
                             "(free) and re-run")
    vpc_id = vpcs[0]["VpcId"]
    offered = {o["Location"] for o in ec2.describe_instance_type_offerings(
        LocationType="availability-zone", Filters=[{"Name": "instance-type", "Values": [instance_type]}])
        ["InstanceTypeOfferings"]}
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]},
                                            {"Name": "default-for-az", "Values": ["true"]}])["Subnets"]
    usable = sorted((s for s in subnets if s["AvailabilityZone"] in offered), key=lambda s: s["AvailabilityZone"])
    if not usable:
        raise BootstrapError(f"{instance_type} is not offered in any default subnet AZ of {aws.region}")
    return vpc_id, usable[0]["SubnetId"]


def desired_ingress(ssh_cidr: str | None) -> list[dict[str, Any]]:
    rules = []
    for port, desc in ((80, "HTTP (ACME challenge + redirect)"), (443, "HTTPS panel")):
        rules.append({"IpProtocol": "tcp", "FromPort": port, "ToPort": port,
                      "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": desc}],
                      "Ipv6Ranges": [{"CidrIpv6": "::/0", "Description": desc}]})
    if ssh_cidr:
        rules.append({"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                      "IpRanges": [{"CidrIp": ssh_cidr, "Description": "SSH (prefer SSM Session Manager)"}]})
    return rules


def _rule_keys(perms: Iterable[dict[str, Any]]) -> set[tuple[str, int, int, str]]:
    keys = set()
    for p in perms:
        for r in p.get("IpRanges", []):
            keys.add((p["IpProtocol"], p.get("FromPort", -1), p.get("ToPort", -1), r["CidrIp"]))
        for r in p.get("Ipv6Ranges", []):
            keys.add((p["IpProtocol"], p.get("FromPort", -1), p.get("ToPort", -1), r["CidrIpv6"]))
    return keys


def _perm_from_key(key: tuple[str, int, int, str]) -> dict[str, Any]:
    proto, lo, hi, cidr = key
    rng = {"Ipv6Ranges": [{"CidrIpv6": cidr}]} if ":" in cidr else {"IpRanges": [{"CidrIp": cidr}]}
    return {"IpProtocol": proto, "FromPort": lo, "ToPort": hi, **rng}


def ensure_security_group(aws: Aws, vpc_id: str, ssh_cidr: str | None) -> str:
    ec2 = aws.client("ec2")
    found = ec2.describe_security_groups(Filters=[*tag_filter(SG_NAME), {"Name": "vpc-id", "Values": [vpc_id]}])
    groups = found["SecurityGroups"]
    if groups:
        sg = groups[0]
        sg_id = sg["GroupId"]
        current = _rule_keys(sg.get("IpPermissions", []))
    else:
        sg_id = ec2.create_security_group(
            GroupName=SG_NAME, Description="SmartSched pod: 80/443 public, 22 only from --ssh-cidr", VpcId=vpc_id,
            TagSpecifications=[{"ResourceType": "security-group", "Tags": tags(SG_NAME)}])["GroupId"]
        log(f"security group {sg_id} created")
        current = set()
    want = _rule_keys(desired_ingress(ssh_cidr))
    add, remove = want - current, current - want
    if remove:
        ec2.revoke_security_group_ingress(GroupId=sg_id, IpPermissions=[_perm_from_key(k) for k in sorted(remove)])
        log(f"security group {sg_id}: revoked {sorted(remove)}")
    if add:
        desired = {k: p for p in desired_ingress(ssh_cidr) for k in _rule_keys([p])}
        ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=[desired[k] for k in sorted(add)])
    return str(sg_id)


def ensure_eip(aws: Aws, instance_id: str | None = None) -> tuple[str, str]:
    """Reuse the tagged EIP; release extra unassociated tagged EIPs so none is left orphaned."""
    ec2 = aws.client("ec2")
    addrs = ec2.describe_addresses(Filters=tag_filter())["Addresses"]
    keep = None
    for a in addrs:
        if instance_id and a.get("InstanceId") == instance_id:
            keep = a
    if keep is None and addrs:
        keep = min(addrs, key=lambda a: (a.get("AssociationId") is not None, a["AllocationId"]))
    for a in addrs:
        if keep is not None and a["AllocationId"] == keep["AllocationId"]:
            continue
        if a.get("AssociationId"):
            log(f"warning: extra tagged EIP {a['PublicIp']} is associated elsewhere; leaving it (run `down`)")
            continue
        ec2.release_address(AllocationId=a["AllocationId"])
        log(f"released orphaned EIP {a['PublicIp']}")
    if keep is None:
        keep = ec2.allocate_address(Domain="vpc", TagSpecifications=[{"ResourceType": "elastic-ip",
                                                                       "Tags": tags(EIP_NAME)}])
        log(f"allocated EIP {keep['PublicIp']}")
    return str(keep["AllocationId"]), str(keep["PublicIp"])


# ------------------------------------------------------------------------------------------------
# instance
# ------------------------------------------------------------------------------------------------
def resolve_ami(aws: Aws, arch: str) -> tuple[str, str]:
    name = f"/aws/service/canonical/ubuntu/server/24.04/stable/current/{arch}/hvm/ebs-gp3/ami-id"
    ami = aws.client("ssm").get_parameter(Name=name)["Parameter"]["Value"]
    image = aws.client("ec2").describe_images(ImageIds=[ami])["Images"][0]
    return str(ami), str(image.get("RootDeviceName", "/dev/sda1"))


def find_instances(aws: Aws, region: str | None = None) -> list[dict[str, Any]]:
    ec2 = aws.client("ec2", region)
    resp = ec2.describe_instances(Filters=[*tag_filter(), {"Name": "instance-state-name",
                                                          "Values": ["pending", "running", "stopping", "stopped"]}])
    return [i for r in resp["Reservations"] for i in r["Instances"]]


def render_user_data(s: Settings, domain: str, template: Path | None = None) -> str:
    text = (template or HERE / "user-data.sh.tmpl").read_text(encoding="utf-8")
    values = {
        "REGION": s.region, "PANEL_DOMAIN": domain, "ADMIN_EMAIL": s.admin_email, "ACME_EMAIL": s.acme_email,
        "REPO": s.repo, "DEPLOY_BRANCH": s.deploy_branch, "CI_BRANCHES": ",".join(s.ci_branches),
        "SSM_PREFIX": SSM_PREFIX, "IDLE_ALARM": ALARM_NAME, "IDLE_MINUTES": str(s.idle_minutes),
        "IDLE_CPU": str(s.idle_cpu_percent), "DOCKER_VERSION": s.docker_version,
    }
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", shlex.quote(v))
    if "@@" in text:
        raise BootstrapError("unrendered @@placeholder@@ left in user-data")
    if len(text.encode()) > 16 * 1024:
        raise BootstrapError("user-data exceeds the 16 KB EC2 limit")
    return text


def launch_instance(aws: Aws, s: Settings, subnet_id: str, sg_id: str, user_data: str,
                    sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    ec2 = aws.client("ec2")
    ami, root = resolve_ami(aws, arch_for(s.instance_type))
    params: dict[str, Any] = {
        "ImageId": ami, "InstanceType": s.instance_type, "MinCount": 1, "MaxCount": 1,
        "SubnetId": subnet_id, "SecurityGroupIds": [sg_id],
        "IamInstanceProfile": {"Name": PROFILE_NAME},
        "UserData": user_data,
        "BlockDeviceMappings": [{"DeviceName": root, "Ebs": {
            "VolumeSize": s.volume_gb, "VolumeType": "gp3", "DeleteOnTermination": True, "Encrypted": True}}],
        # IMDSv2 only; hop limit 1 keeps the role credentials away from CI containers on docker bridges.
        "MetadataOptions": {"HttpTokens": "required", "HttpPutResponseHopLimit": 1, "HttpEndpoint": "enabled"},
        "InstanceInitiatedShutdownBehavior": "stop",
        "TagSpecifications": [
            {"ResourceType": "instance", "Tags": tags(INSTANCE_NAME)},
            {"ResourceType": "volume", "Tags": tags(f"{INSTANCE_NAME}-root")},
            {"ResourceType": "network-interface", "Tags": tags(f"{INSTANCE_NAME}-eni")},
        ],
    }
    if s.instance_type.startswith("t"):
        params["CreditSpecification"] = {"CpuCredits": s.cpu_credits}
    for attempt in range(12):  # a fresh instance profile takes a few seconds to propagate
        try:
            inst = ec2.run_instances(**params)["Instances"][0]
            log(f"launched {inst['InstanceId']} ({s.instance_type}, {ami})")
            return dict(inst)
        except Exception as exc:
            if error_code(exc) == "InvalidParameterValue" and "iamInstanceProfile" in str(exc) and attempt < 11:
                sleep(5)
                continue
            raise
    raise BootstrapError("run_instances kept failing")  # pragma: no cover


def instance_state(aws: Aws, instance_id: str) -> str:
    try:
        resp = aws.client("ec2").describe_instances(InstanceIds=[instance_id])
    except Exception as exc:
        if error_code(exc) == "InvalidInstanceID.NotFound":  # eventual consistency right after RunInstances
            return "pending"
        raise
    return str(resp["Reservations"][0]["Instances"][0]["State"]["Name"])


def associate_eip(aws: Aws, alloc_id: str, instance_id: str) -> None:
    ec2 = aws.client("ec2")
    addr = ec2.describe_addresses(AllocationIds=[alloc_id])["Addresses"][0]
    if addr.get("InstanceId") == instance_id:
        return
    ec2.associate_address(AllocationId=alloc_id, InstanceId=instance_id, AllowReassociation=True)
    log(f"EIP {addr['PublicIp']} -> {instance_id}")


# ------------------------------------------------------------------------------------------------
# CloudWatch idle stop
# ------------------------------------------------------------------------------------------------
def idle_alarm_params(region: str, instance_id: str, minutes: int = 60, cpu: float = 5.0) -> dict[str, Any]:
    periods = max(1, minutes // 5)
    return {
        "AlarmName": ALARM_NAME,
        "AlarmDescription": (f"Stop the SmartSched pod when CPU < {cpu}% for {minutes} min. Pod CI disables this "
                             "alarm's actions while a CI job runs (no stop mid-job) and re-enables them after."),
        "Namespace": "AWS/EC2", "MetricName": "CPUUtilization",
        "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
        "Statistic": "Average", "Period": 300, "EvaluationPeriods": periods, "DatapointsToAlarm": periods,
        "Threshold": cpu, "ComparisonOperator": "LessThanThreshold",
        "TreatMissingData": "missing",  # a stopped instance sends nothing: keep the state, no flapping
        "ActionsEnabled": True,
        "AlarmActions": [f"arn:aws:automate:{region}:ec2:stop"],
        "Tags": tags(ALARM_NAME),
    }


def ensure_idle_alarm(aws: Aws, instance_id: str, s: Settings) -> None:
    aws.client("cloudwatch").put_metric_alarm(**idle_alarm_params(s.region, instance_id, s.idle_minutes,
                                                                  s.idle_cpu_percent))
    log(f"alarm {ALARM_NAME} set (CPU < {s.idle_cpu_percent}% for {s.idle_minutes} min -> stop)")


# ------------------------------------------------------------------------------------------------
# Budgets
# ------------------------------------------------------------------------------------------------
def budget_definition(amount: float) -> dict[str, Any]:
    return {"BudgetName": BUDGET_NAME, "BudgetType": "COST", "TimeUnit": "MONTHLY",
            "BudgetLimit": {"Amount": f"{amount:.2f}", "Unit": "USD"}}


def budget_notifications() -> list[dict[str, Any]]:
    return [{"NotificationType": kind, "ComparisonOperator": "GREATER_THAN", "Threshold": pct,
             "ThresholdType": "PERCENTAGE"} for kind, pct in BUDGET_ALERTS]


def ensure_budget(aws: Aws, account: str, s: Settings) -> None:
    b = aws.client("budgets")
    subscriber = [{"SubscriptionType": "EMAIL", "Address": s.alert_email}]
    try:
        cur = b.describe_budget(AccountId=account, BudgetName=BUDGET_NAME)["Budget"]
    except Exception as exc:
        if error_code(exc) != "NotFoundException":
            raise
        b.create_budget(AccountId=account, Budget=budget_definition(s.budget_usd),
                        NotificationsWithSubscribers=[{"Notification": n, "Subscribers": subscriber}
                                                      for n in budget_notifications()],
                        ResourceTags=[{"Key": TAG_KEY, "Value": TAG_VALUE}])
        log(f"budget {BUDGET_NAME} created (${s.budget_usd:.0f}/month, alerts to {s.alert_email})")
        return
    if float(cur["BudgetLimit"]["Amount"]) != float(s.budget_usd):
        b.update_budget(AccountId=account, NewBudget=budget_definition(s.budget_usd))
        log(f"budget {BUDGET_NAME} limit -> ${s.budget_usd:.0f}")
    have = b.describe_notifications_for_budget(AccountId=account, BudgetName=BUDGET_NAME)["Notifications"]
    have_keys = {(n["NotificationType"], float(n["Threshold"])) for n in have}
    for n in budget_notifications():
        key = (n["NotificationType"], float(n["Threshold"]))
        if key not in have_keys:
            b.create_notification(AccountId=account, BudgetName=BUDGET_NAME, Notification=n, Subscribers=subscriber)
            continue
        subs = b.describe_subscribers_for_notification(AccountId=account, BudgetName=BUDGET_NAME,
                                                       Notification=n)["Subscribers"]
        if not any(x["Address"] == s.alert_email for x in subs):
            b.create_subscriber(AccountId=account, BudgetName=BUDGET_NAME, Notification=n, Subscriber=subscriber[0])
    log(f"budget {BUDGET_NAME} ok")


def budget_action_definition(region: str, instance_id: str) -> dict[str, Any]:
    return {"SsmActionDefinition": {"ActionSubType": "STOP_EC2_INSTANCES", "Region": region,
                                    "InstanceIds": [instance_id]}}


def ensure_budget_action(aws: Aws, account: str, s: Settings, role_arn: str, instance_id: str) -> str:
    b = aws.client("budgets")
    want = budget_action_definition(s.region, instance_id)
    threshold = {"ActionThresholdValue": 100.0, "ActionThresholdType": "PERCENTAGE"}
    subscribers = [{"SubscriptionType": "EMAIL", "Address": s.alert_email}]
    actions = b.describe_budget_actions_for_budget(AccountId=account, BudgetName=BUDGET_NAME)["Actions"]
    for a in actions:
        ssm_def = a.get("Definition", {}).get("SsmActionDefinition", {})
        if a.get("ActionType") == "RUN_SSM_DOCUMENTS" and ssm_def.get("ActionSubType") == "STOP_EC2_INSTANCES":
            if ssm_def.get("InstanceIds") != [instance_id] or ssm_def.get("Region") != s.region \
                    or a.get("ExecutionRoleArn") != role_arn:
                b.update_budget_action(AccountId=account, BudgetName=BUDGET_NAME, ActionId=a["ActionId"],
                                       NotificationType="ACTUAL", ActionThreshold=threshold, Definition=want,
                                       ExecutionRoleArn=role_arn, ApprovalModel="AUTOMATIC", Subscribers=subscribers)
                log(f"budget action {a['ActionId']} now stops {instance_id}")
            return str(a["ActionId"])
    for attempt in range(6):  # the new budget-action role needs a few seconds before Budgets can assume it
        try:
            resp = b.create_budget_action(
                AccountId=account, BudgetName=BUDGET_NAME, NotificationType="ACTUAL", ActionType="RUN_SSM_DOCUMENTS",
                ActionThreshold=threshold, Definition=want, ExecutionRoleArn=role_arn, ApprovalModel="AUTOMATIC",
                Subscribers=subscribers, ResourceTags=[{"Key": TAG_KEY, "Value": TAG_VALUE}])
            log(f"budget action {resp['ActionId']} created: stop {instance_id} at 100 % actual")
            return str(resp["ActionId"])
        except Exception as exc:
            if error_code(exc) in ("AccessDeniedException", "InvalidParameterException") and attempt < 5:
                time.sleep(10)
                continue
            raise
    raise BootstrapError("could not create the budget action")  # pragma: no cover


# ------------------------------------------------------------------------------------------------
# SSM parameters
# ------------------------------------------------------------------------------------------------
def put_parameter(aws: Aws, name: str, value: str, secure: bool = False) -> None:
    ssm = aws.client("ssm")
    kind = "SecureString" if secure else "String"
    try:
        ssm.put_parameter(Name=name, Value=value, Type=kind, Tags=[{"Key": TAG_KEY, "Value": TAG_VALUE}])
    except Exception as exc:
        if error_code(exc) != "ParameterAlreadyExists":
            raise
        ssm.put_parameter(Name=name, Value=value, Type=kind, Overwrite=True)


def list_parameters(aws: Aws, region: str | None = None) -> list[str]:
    ssm = aws.client("ssm", region)
    names: list[str] = []
    token = None
    while True:
        kw: dict[str, Any] = {"Path": SSM_PREFIX, "Recursive": True, "WithDecryption": False, "MaxResults": 10}
        if token:
            kw["NextToken"] = token
        resp = ssm.get_parameters_by_path(**kw)
        names += [p["Name"] for p in resp.get("Parameters", [])]
        token = resp.get("NextToken")
        if not token:
            return sorted(names)


def parameter_names() -> dict[str, str]:
    return {
        "panel_url": f"{SSM_PREFIX}/panel_url",
        "admin_email": f"{SSM_PREFIX}/admin_email",
        "admin_password": f"{SSM_PREFIX}/admin_password",
        "github_token": f"{SSM_PREFIX}/github_token",
        "ci_basic_auth": f"{SSM_PREFIX}/ci/basic_auth",
        "app_secrets": f"{SSM_PREFIX}/app/*",
    }


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------
@dataclass
class UpResult:
    region: str
    account: str
    instance_id: str
    public_ip: str
    panel_url: str
    admin_email: str
    estimate: dict[str, float]
    parameters: dict[str, str] = field(default_factory=parameter_names)

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "read_admin_password": read_password_hint(self.region)}


def read_password_hint(region: str) -> str:
    return (f"aws ssm get-parameter --region {region} --name {SSM_PREFIX}/admin_password --with-decryption "
            "--query Parameter.Value --output text")


def cmd_up(aws: Aws, s: Settings, account: str, sleep: Callable[[float], None] = time.sleep) -> UpResult:
    pod_profile = ensure_pod_role(aws, account, s.region)
    log(f"instance profile {pod_profile}")
    vpc_id, subnet_id = default_subnet(aws, s.instance_type)
    sg_id = ensure_security_group(aws, vpc_id, s.ssh_cidr)

    existing = find_instances(aws)
    if len(existing) > 1:
        raise BootstrapError(f"{len(existing)} tagged instances found ({[i['InstanceId'] for i in existing]}); "
                             "run `down` or terminate the extras first")
    inst = existing[0] if existing else None
    alloc_id, public_ip = ensure_eip(aws, inst["InstanceId"] if inst else None)
    domain = panel_domain(public_ip)
    if inst is None:
        inst = launch_instance(aws, s, subnet_id, sg_id, render_user_data(s, domain), sleep=sleep)
    else:
        log(f"instance {inst['InstanceId']} exists ({inst['State']['Name']}, {inst['InstanceType']})")
        if inst["InstanceType"] != s.instance_type:
            log(f"warning: running type {inst['InstanceType']} != requested {s.instance_type}; `down` + `up` to change")
        if inst["State"]["Name"] in ("stopped", "stopping"):
            wait_for(lambda: instance_state(aws, inst["InstanceId"]) == "stopped", "instance stopped", sleep=sleep)
            aws.client("ec2").start_instances(InstanceIds=[inst["InstanceId"]])
            log(f"started {inst['InstanceId']}")
    iid = inst["InstanceId"]
    wait_for(lambda: instance_state(aws, iid) == "running", f"{iid} running", sleep=sleep)
    associate_eip(aws, alloc_id, iid)
    ensure_pod_role(aws, account, s.region, instance_id=iid)  # StopInstances on itself only
    ensure_idle_alarm(aws, iid, s)
    ensure_budget(aws, account, s)
    if s.budget_action:
        ensure_budget_action(aws, account, s, ensure_budget_role(aws, account), iid)
    url = f"https://{domain}"
    put_parameter(aws, f"{SSM_PREFIX}/panel_url", url)
    hourly, _ = ec2_hourly_price(aws, s.region, s.instance_type)
    gp3, _ = gp3_price(aws, s.region)
    return UpResult(region=s.region, account=account, instance_id=iid, public_ip=public_ip, panel_url=url,
                    admin_email=s.admin_email, estimate=estimate_monthly(hourly, gp3, s.volume_gb))


def orphans(aws: Aws, region: str | None = None) -> dict[str, list[str]]:
    ec2 = aws.client("ec2", region)
    vols = ec2.describe_volumes(Filters=[*tag_filter(), {"Name": "status", "Values": ["available"]}])["Volumes"]
    addrs = ec2.describe_addresses(Filters=tag_filter())["Addresses"]
    return {"volumes": [v["VolumeId"] for v in vols],
            "eips": [a["PublicIp"] for a in addrs if not a.get("AssociationId")]}


def cmd_status(aws: Aws, s: Settings, account: str) -> dict[str, Any]:
    out: dict[str, Any] = {"account": account, "region": s.region, "parameters": parameter_names()}
    insts = find_instances(aws)
    hourly, src = ec2_hourly_price(aws, s.region, insts[0]["InstanceType"] if insts else s.instance_type)
    gp3, _ = gp3_price(aws, s.region)
    out["instances"] = [{"id": i["InstanceId"], "type": i["InstanceType"], "state": i["State"]["Name"],
                         "public_ip": i.get("PublicIpAddress"), "launched": str(i.get("LaunchTime"))} for i in insts]
    addrs = aws.client("ec2").describe_addresses(Filters=tag_filter())["Addresses"]
    out["eips"] = [{"ip": a["PublicIp"], "instance": a.get("InstanceId")} for a in addrs]
    if addrs:
        out["panel_url"] = f"https://{panel_domain(addrs[0]['PublicIp'])}"
    alarms = aws.client("cloudwatch").describe_alarms(AlarmNames=[ALARM_NAME])["MetricAlarms"]
    out["idle_alarm"] = ({"state": alarms[0]["StateValue"], "actions_enabled": alarms[0]["ActionsEnabled"]}
                         if alarms else None)
    try:
        b = aws.client("budgets").describe_budget(AccountId=account, BudgetName=BUDGET_NAME)["Budget"]
        spend = b.get("CalculatedSpend", {})
        out["budget"] = {"limit": b["BudgetLimit"]["Amount"],
                         "actual": spend.get("ActualSpend", {}).get("Amount"),
                         "forecast": spend.get("ForecastedSpend", {}).get("Amount")}
    except Exception as exc:
        if error_code(exc) != "NotFoundException":
            raise
        out["budget"] = None
    running = any(i["State"]["Name"] in ("pending", "running") for i in insts)
    vol_gb = s.volume_gb if insts else 0
    out["estimated_monthly_usd"] = {
        "current_state": estimate_monthly(hourly, gp3, vol_gb, running=running, eips=len(addrs),
                                          alarms=1 if alarms else 0),
        "if_running_24x7": estimate_monthly(hourly, gp3, s.volume_gb, running=True, eips=max(1, len(addrs))),
        "price_source": src,
    }
    out["orphans"] = orphans(aws)
    others = {}
    for region in PRICE_REGIONS:
        if region != s.region:
            found = find_instances(aws, region)
            if found:
                others[region] = [i["InstanceId"] for i in found]
    out["tagged_instances_in_other_regions"] = others
    return out


def cmd_stop(aws: Aws, sleep: Callable[[float], None] = time.sleep) -> list[str]:
    ids = [i["InstanceId"] for i in find_instances(aws) if i["State"]["Name"] in ("pending", "running")]
    if ids:
        aws.client("ec2").stop_instances(InstanceIds=ids)
        for iid in ids:
            wait_for(lambda iid=iid: instance_state(aws, iid) == "stopped", f"{iid} stopped", sleep=sleep)
    return ids


def cmd_start(aws: Aws, sleep: Callable[[float], None] = time.sleep) -> list[str]:
    insts = find_instances(aws)
    ids = [i["InstanceId"] for i in insts if i["State"]["Name"] in ("stopped", "stopping")]
    for iid in ids:
        wait_for(lambda iid=iid: instance_state(aws, iid) == "stopped", f"{iid} stopped", sleep=sleep)
    if ids:
        aws.client("ec2").start_instances(InstanceIds=ids)
        for iid in ids:
            wait_for(lambda iid=iid: instance_state(aws, iid) == "running", f"{iid} running", sleep=sleep)
    for inst in insts:  # the EIP survives stop/start; re-associate defensively
        addrs = aws.client("ec2").describe_addresses(Filters=tag_filter())["Addresses"]
        if addrs and addrs[0].get("InstanceId") != inst["InstanceId"]:
            associate_eip(aws, addrs[0]["AllocationId"], inst["InstanceId"])
    return ids


def _delete_role(iam: Any, name: str, profile: str | None = None) -> None:
    if profile:
        try:
            prof = iam.get_instance_profile(InstanceProfileName=profile)["InstanceProfile"]
            for r in prof.get("Roles", []):
                iam.remove_role_from_instance_profile(InstanceProfileName=profile, RoleName=r["RoleName"])
            iam.delete_instance_profile(InstanceProfileName=profile)
            log(f"deleted instance profile {profile}")
        except Exception as exc:
            if error_code(exc) != "NoSuchEntity":
                raise
    try:
        iam.get_role(RoleName=name)
    except Exception as exc:
        if error_code(exc) == "NoSuchEntity":
            return
        raise
    for pname in iam.list_role_policies(RoleName=name)["PolicyNames"]:
        iam.delete_role_policy(RoleName=name, PolicyName=pname)
    for p in iam.list_attached_role_policies(RoleName=name)["AttachedPolicies"]:
        iam.detach_role_policy(RoleName=name, PolicyArn=p["PolicyArn"])
    iam.delete_role(RoleName=name)
    log(f"deleted IAM role {name}")


def down_region(aws: Aws, region: str, keep_parameters: bool = False,
                sleep: Callable[[float], None] = time.sleep) -> dict[str, list[str]]:
    """Delete every tagged regional resource (instance, EIP, volumes, SG, alarm, parameters)."""
    ec2 = aws.client("ec2", region)
    done: dict[str, list[str]] = {"instances": [], "eips": [], "volumes": [], "security_groups": [],
                                  "alarms": [], "parameters": []}
    alarms = aws.client("cloudwatch", region).describe_alarms(AlarmNamePrefix="smartsched-")["MetricAlarms"]
    if alarms:
        names = [a["AlarmName"] for a in alarms]
        aws.client("cloudwatch", region).delete_alarms(AlarmNames=names)
        done["alarms"] = names
    ids = [i["InstanceId"] for i in find_instances(aws, region)]
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
        done["instances"] = ids

        def all_terminated() -> bool:
            resp = ec2.describe_instances(InstanceIds=ids)
            return all(i["State"]["Name"] == "terminated" for r in resp["Reservations"] for i in r["Instances"])

        wait_for(all_terminated, f"{ids} terminated", sleep=sleep)
    for a in ec2.describe_addresses(Filters=tag_filter())["Addresses"]:
        if a.get("AssociationId"):
            ec2.disassociate_address(AssociationId=a["AssociationId"])
        ec2.release_address(AllocationId=a["AllocationId"])
        done["eips"].append(a["PublicIp"])
    for v in ec2.describe_volumes(Filters=[*tag_filter(), {"Name": "status", "Values": ["available"]}])["Volumes"]:
        ec2.delete_volume(VolumeId=v["VolumeId"])
        done["volumes"].append(v["VolumeId"])
    for sg in ec2.describe_security_groups(Filters=tag_filter())["SecurityGroups"]:
        for attempt in range(12):  # ENIs of a just-terminated instance release the SG asynchronously
            try:
                ec2.delete_security_group(GroupId=sg["GroupId"])
                done["security_groups"].append(sg["GroupId"])
                break
            except Exception as exc:
                if error_code(exc) == "DependencyViolation" and attempt < 11:
                    sleep(10)
                    continue
                raise
    if not keep_parameters:
        names = list_parameters(aws, region)
        for i in range(0, len(names), 10):
            aws.client("ssm", region).delete_parameters(Names=names[i:i + 10])
        done["parameters"] = names
    return done


def cmd_down(aws: Aws, account: str, regions: Iterable[str], keep_parameters: bool = False,
             delete_budget: bool = False, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Delete every tagged resource. The budget itself predates the pod and keeps protecting the account,
    so only its stop action is removed (the action's role is deleted below) unless delete_budget."""
    out: dict[str, Any] = {}
    b = aws.client("budgets")
    try:
        actions = b.describe_budget_actions_for_budget(AccountId=account, BudgetName=BUDGET_NAME)["Actions"]
        for a in actions:
            b.delete_budget_action(AccountId=account, BudgetName=BUDGET_NAME, ActionId=a["ActionId"])
        out["budget_actions_deleted"] = [a["ActionId"] for a in actions]
        if delete_budget:
            b.delete_budget(AccountId=account, BudgetName=BUDGET_NAME)
        out["budget"] = "deleted" if delete_budget else f"kept ({BUDGET_NAME})"
    except Exception as exc:
        if error_code(exc) != "NotFoundException":
            raise
        out["budget"] = None
    for region in dict.fromkeys(regions):
        out[region] = down_region(aws, region, keep_parameters=keep_parameters, sleep=sleep)
    iam = aws.client("iam")
    _delete_role(iam, ROLE_NAME, PROFILE_NAME)
    _delete_role(iam, BUDGET_ROLE_NAME)
    leftovers: dict[str, list[str]] = {}
    for region in dict.fromkeys(regions):
        try:
            resp = aws.client("resourcegroupstaggingapi", region).get_resources(
                TagFilters=[{"Key": TAG_KEY, "Values": [TAG_VALUE]}])
        except Exception as exc:  # noqa: BLE001 - tag:GetResources is optional for the bootstrap role
            leftovers[region] = [f"not checked ({error_code(exc) or exc}); grant tag:GetResources to verify"]
            continue
        # terminated instances stay visible for ~1 h and cost nothing; everything else is a leftover
        arns = [r["ResourceARN"] for r in resp.get("ResourceTagMappingList", [])
                if ":instance/" not in r["ResourceARN"]]
        if arns:
            leftovers[region] = arns
    out["leftovers"] = leftovers
    return out


def cmd_cost(aws: Aws, s: Settings, account: str, today: dt.date | None = None) -> dict[str, Any]:
    today = today or dt.datetime.now(dt.UTC).date()
    start = today.replace(day=1).isoformat()
    end = (today + dt.timedelta(days=1)).isoformat()
    ce = aws.client("ce")
    out: dict[str, Any] = {"period": {"start": start, "end": end}}

    def total(resp: dict[str, Any]) -> float:
        return round(sum(float(r["Total"]["UnblendedCost"]["Amount"]) for r in resp["ResultsByTime"]), 2)

    out["account_month_to_date_usd"] = total(ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end}, Granularity="MONTHLY", Metrics=["UnblendedCost"]))
    # Needs the Project cost-allocation tag activated (Billing console); 0 until then.
    out["tagged_month_to_date_usd"] = total(ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end}, Granularity="MONTHLY", Metrics=["UnblendedCost"],
        Filter={"Tags": {"Key": TAG_KEY, "Values": [TAG_VALUE]}}))
    st = cmd_status(aws, s, account)
    out["budget"] = st["budget"]
    out["estimated_monthly_usd"] = st["estimated_monthly_usd"]
    return out


def cmd_plan(s: Settings, public_ip: str = "203.0.113.10") -> dict[str, Any]:
    """Offline: no AWS call. Shows what `up` would create, with fallback prices."""
    hourly = FALLBACK_HOURLY.get((s.region, s.instance_type), 0.0)
    gp3 = FALLBACK_GP3_GB_MONTH.get(s.region, 0.08)
    return {
        "region": s.region,
        "resources": {
            "iam_roles": [ROLE_NAME, BUDGET_ROLE_NAME], "instance_profile": PROFILE_NAME,
            "security_group": {"name": SG_NAME, "ingress": desired_ingress(s.ssh_cidr)},
            "elastic_ip": EIP_NAME,
            "instance": {"name": INSTANCE_NAME, "type": s.instance_type, "arch": arch_for(s.instance_type),
                         "ami": "Ubuntu 24.04 (SSM public parameter, resolved at run time)",
                         "root_volume_gb": s.volume_gb, "volume_type": "gp3", "cpu_credits": s.cpu_credits},
            "alarm": idle_alarm_params(s.region, "i-PLACEHOLDER", s.idle_minutes, s.idle_cpu_percent),
            "budget": {**budget_definition(s.budget_usd), "notifications": budget_notifications(),
                       "subscriber": s.alert_email, "stop_action_at_percent": 100 if s.budget_action else None},
            "pod_role_policy": pod_role_policy("123456789012", s.region, "i-PLACEHOLDER"),
            "parameters": parameter_names(),
        },
        "panel_url_example": f"https://{panel_domain(public_ip)}",
        "estimated_monthly_usd_fallback_prices": estimate_monthly(hourly, gp3, s.volume_gb),
        "user_data_bytes": len(render_user_data(s, panel_domain(public_ip)).encode()),
    }


# ------------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="smartsched_aws.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["up", "status", "stop", "start", "down", "cost", "plan", "preflight",
                                       "put-github-token", "render-user-data"])
    p.add_argument("--region", default=None,
                   help=f"AWS region, or 'auto' = cheaper of {'/'.join(NEAR_TURKIYE)} (default: $AWS_REGION, "
                        f"$AWS_DEFAULT_REGION, else {DEFAULT_REGION})")
    p.add_argument("--instance-type", default="t4g.large")
    p.add_argument("--volume-gb", type=int, default=40)
    p.add_argument("--ssh-cidr", default=None, help="open 22/tcp to this CIDR (off by default; use SSM)")
    p.add_argument("--budget-usd", type=float, default=100.0)
    p.add_argument("--alert-email", default=DEFAULT_EMAIL)
    p.add_argument("--admin-email", default=DEFAULT_EMAIL)
    p.add_argument("--acme-email", default=DEFAULT_EMAIL)
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--deploy-branch", default=DEFAULT_DEPLOY_BRANCH)
    p.add_argument("--ci-branches", default=",".join(DEFAULT_CI_BRANCHES))
    p.add_argument("--cpu-credits", choices=["standard", "unlimited"], default="standard",
                   help="burstable credit mode; standard never bills surplus CPU credits")
    p.add_argument("--idle-minutes", type=int, default=60)
    p.add_argument("--docker-version", default="", help="pin docker-ce, e.g. 5:28.5.1-1~ubuntu.24.04~noble")
    p.add_argument("--no-budget-action", action="store_true")
    p.add_argument("--yes", action="store_true", help="confirm `down`")
    p.add_argument("--keep-parameters", action="store_true", help="`down` keeps /smartsched/* SSM parameters")
    p.add_argument("--delete-budget", action="store_true", help=f"`down` also deletes the budget {BUDGET_NAME}")
    p.add_argument("--from-env", default="POD_GITHUB_TOKEN", help="env var holding the token (put-github-token)")
    p.add_argument("--json", action="store_true", help="print the result as JSON on stdout")
    p.add_argument("--output-json", default=None, help="also write the (secret-free) result to this file")
    return p


def resolve_region(arg: str | None, env: dict[str, str] | None = None) -> str | None:
    """None means 'auto' (needs prices)."""
    env = os.environ if env is None else env
    value = arg or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or DEFAULT_REGION
    return None if value == "auto" else value


def settings_from_args(a: argparse.Namespace, region: str) -> Settings:
    return Settings(region=region, instance_type=a.instance_type, volume_gb=a.volume_gb, ssh_cidr=a.ssh_cidr,
                    budget_usd=a.budget_usd, alert_email=a.alert_email, admin_email=a.admin_email,
                    acme_email=a.acme_email, repo=a.repo, deploy_branch=a.deploy_branch,
                    ci_branches=tuple(b for b in a.ci_branches.split(",") if b), cpu_credits=a.cpu_credits,
                    idle_minutes=a.idle_minutes, docker_version=a.docker_version,
                    budget_action=not a.no_budget_action)


def emit(result: Any, a: argparse.Namespace) -> None:
    text = json.dumps(result, indent=2, default=str)
    if a.output_json:
        Path(a.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    region = resolve_region(a.region)
    try:
        if a.command in ("plan", "render-user-data"):
            s = settings_from_args(a, region or NEAR_TURKIYE[0])
            if a.command == "render-user-data":
                sys.stdout.write(render_user_data(s, panel_domain("203.0.113.10")))
            else:
                emit(cmd_plan(s), a)
            return 0
        aws = Aws(region or GLOBAL_REGION)
        ident = preflight(aws)
        log(f"account {ident['account']} as {ident['arn']}")
        if a.command == "preflight":
            emit(ident, a)
            return 0
        if a.command in ("up", "status", "cost"):
            prices = price_table(aws)
            log("on-demand Linux prices:\n" + format_price_table(prices))
            if region is None:
                region = choose_region(prices, a.instance_type)
                log(f"--region auto -> {region} (cheapest of {', '.join(NEAR_TURKIYE)} for {a.instance_type})")
        region = region or DEFAULT_REGION
        aws = Aws(region, session=aws._session, clients=aws._clients)
        s = settings_from_args(a, region)
        if a.command == "up":
            res = cmd_up(aws, s, ident["account"])
            log(f"panel: {res.panel_url} (TLS via Caddy + Let's Encrypt once the pod finishes booting, ~10-15 min)")
            log(f"admin: {res.admin_email}; password: {read_password_hint(region)}")
            emit(res.as_dict(), a)
        elif a.command == "status":
            emit(cmd_status(aws, s, ident["account"]), a)
        elif a.command == "cost":
            emit(cmd_cost(aws, s, ident["account"]), a)
        elif a.command == "stop":
            emit({"stopped": cmd_stop(aws)}, a)
        elif a.command == "start":
            emit({"started": cmd_start(aws), "parameters": parameter_names()}, a)
        elif a.command == "down":
            if not a.yes:
                raise BootstrapError("`down` deletes the pod, its data and all tagged resources: pass --yes")
            emit(cmd_down(aws, ident["account"], [region, *PRICE_REGIONS], keep_parameters=a.keep_parameters,
                          delete_budget=a.delete_budget), a)
        elif a.command == "put-github-token":
            token = os.environ.get(a.from_env, "").strip()
            if not token:
                log(f"warning: ${a.from_env} is empty; the pod waits until {SSM_PREFIX}/github_token exists")
                return 0
            put_parameter(aws, f"{SSM_PREFIX}/github_token", token, secure=True)
            emit({"stored": f"{SSM_PREFIX}/github_token", "region": region, "type": "SecureString"}, a)
        return 0
    except BootstrapError as exc:
        log(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
