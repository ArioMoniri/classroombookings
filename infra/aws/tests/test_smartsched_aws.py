"""Planning logic of infra/aws/smartsched_aws.py against botocore Stubber (no network, fake keys)."""

from __future__ import annotations

import datetime as dt
import fnmatch
import json
import subprocess
from typing import Any

import pytest
from awsstub import StubAws, price_item
from botocore.stub import ANY

import smartsched_aws as sa

NOW = dt.datetime(2026, 10, 8, 12, 0, tzinfo=dt.UTC)
ACCOUNT = "123456789012"
EMAIL = sa.DEFAULT_EMAIL
ACTION_ID = "0f3c2c1e-1111-4222-8333-444455556666"
SUBS = [{"SubscriptionType": "EMAIL", "Address": EMAIL}]
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/{sa.BUDGET_ROLE_NAME}"


def role(name: str) -> dict[str, Any]:
    return {"Path": "/", "RoleName": name, "RoleId": "AROAEXAMPLEEXAMPLE01", "CreateDate": NOW,
            "Arn": f"arn:aws:iam::{ACCOUNT}:role/{name}"}


def profile(with_role: bool) -> dict[str, Any]:
    return {"Path": "/", "InstanceProfileName": sa.PROFILE_NAME, "InstanceProfileId": "AIPAEXAMPLEEXAMPLE01",
            "Arn": f"arn:aws:iam::{ACCOUNT}:instance-profile/{sa.PROFILE_NAME}", "CreateDate": NOW,
            "Roles": [role(sa.ROLE_NAME)] if with_role else []}


def instance(state: str = "running", iid: str = "i-0123456789abcdef0") -> dict[str, Any]:
    return {"InstanceId": iid, "InstanceType": "t4g.large", "State": {"Name": state, "Code": 16},
            "LaunchTime": NOW}


def notifications() -> list[dict[str, Any]]:
    return [dict(n) for n in sa.budget_notifications()]


def matches(action: str, policy: dict[str, Any]) -> bool:
    for st in policy["Statement"]:
        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        if st["Effect"] == "Allow" and any(fnmatch.fnmatchcase(action, a) for a in acts):
            return True
    return False


# The inline policy of the EXISTING role smartsched-github-bootstrap (.github/workflows/aws-oidc-bootstrap.yml).
EXISTING_ROLE_POLICY = {"Statement": [
    {"Effect": "Allow", "Action": ["ec2:*", "ssm:*", "cloudwatch:*", "logs:*", "budgets:*", "pricing:GetProducts",
                                   "pricing:DescribeServices", "ce:GetCostAndUsage", "ce:GetCostForecast",
                                   "sts:GetCallerIdentity"]},
    {"Effect": "Allow", "Action": "iam:*"},  # resource-scoped to smartsched-* in AWS
    {"Effect": "Allow", "Action": "iam:CreateServiceLinkedRole"},
]}


# ------------------------------------------------------------------------------------------------
# preflight
# ------------------------------------------------------------------------------------------------
def test_preflight_ok(aws: StubAws) -> None:
    arn = f"arn:aws:sts::{ACCOUNT}:assumed-role/x/y"
    aws.stub("sts").add_response("get_caller_identity", {"Account": ACCOUNT, "Arn": arn, "UserId": "u"})
    assert sa.preflight(aws)["account"] == ACCOUNT


@pytest.mark.parametrize(("code", "needle"), [("ExpiredToken", "EXPIRED"), ("InvalidClientTokenId", "rejected")])
def test_preflight_bad_credentials_fail_fast(aws: StubAws, code: str, needle: str,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_CREDENTIAL_EXPIRATION", raising=False)
    aws.stub("sts").add_client_error("get_caller_identity", service_error_code=code, http_status_code=403)
    with pytest.raises(sa.BootstrapError, match=needle):
        sa.preflight(aws)


def test_credential_expiration_env() -> None:
    assert sa.credential_expiry_warning({}, NOW) is None
    with pytest.raises(sa.BootstrapError, match="expired"):
        sa.credential_expiry_warning({"AWS_CREDENTIAL_EXPIRATION": "2026-10-08T11:00:26Z"}, NOW)
    warn = sa.credential_expiry_warning({"AWS_CREDENTIAL_EXPIRATION": "2026-10-08T12:10:00Z"}, NOW)
    assert warn and "10 min" in warn
    assert sa.credential_expiry_warning({"AWS_CREDENTIAL_EXPIRATION": "2026-10-08T15:00:00Z"}, NOW) is None


def test_main_exits_2_with_message_on_expired_keys(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setenv("AWS_CREDENTIAL_EXPIRATION", "2026-10-08T11:00:26Z")
    monkeypatch.setattr(sa, "Aws", lambda *a, **k: StubAws())
    assert sa.main(["up"]) == 2
    assert "expired" in capsys.readouterr().err


# ------------------------------------------------------------------------------------------------
# pricing / region
# ------------------------------------------------------------------------------------------------
def test_price_table_and_region_choice(aws: StubAws) -> None:
    st = aws.stub("pricing")
    prices = {("us-east-1", "t4g.large"): "0.0672", ("us-east-1", "t3.large"): "0.0832",
              ("eu-central-1", "t4g.large"): "0.0768", ("eu-central-1", "t3.large"): "0.0960",
              ("eu-south-1", "t4g.large"): "0.0744", ("eu-south-1", "t3.large"): "0.0912"}
    for region in sa.PRICE_REGIONS:
        for itype in sa.COMPARE_TYPES:
            st.add_response("get_products", {"PriceList": [price_item(prices[(region, itype)])]},
                            {"ServiceCode": "AmazonEC2", "Filters": ANY, "MaxResults": 10})
    table = sa.price_table(aws)
    aws.assert_done()
    assert table[("eu-south-1", "t4g.large")] == (0.0744, "pricing-api")
    assert sa.choose_region(table, "t4g.large") == "eu-south-1"  # cheaper of the two near Türkiye
    assert sa.choose_region(table, "t3.large") == "eu-south-1"
    assert sa.choose_region(table, "t4g.large", candidates=sa.PRICE_REGIONS) == "us-east-1"
    assert "eu-central-1" in sa.format_price_table(table)


def test_pricing_failure_falls_back_to_table(aws: StubAws) -> None:
    aws.stub("pricing").add_client_error("get_products", service_error_code="AccessDeniedException")
    assert sa.ec2_hourly_price(aws, "us-east-1", "t4g.large") == (0.0672, "fallback-table")


def test_estimate_monthly() -> None:
    est = sa.estimate_monthly(0.0672, 0.08, 40)
    assert est["compute"] == 49.06 and est["ebs_gp3"] == 3.2 and est["public_ipv4"] == 3.65
    assert est["total"] == pytest.approx(49.06 + 3.2 + 3.65 + 0.1 + 0.6)
    stopped = sa.estimate_monthly(0.0672, 0.08, 40, running=False)
    assert stopped["compute"] == 0 and stopped["total"] < 10


def test_region_resolution() -> None:
    assert sa.resolve_region(None, {}) == "us-east-1"
    assert sa.resolve_region(None, {"AWS_DEFAULT_REGION": "eu-central-1"}) == "eu-central-1"
    assert sa.resolve_region("auto", {}) is None
    assert sa.arch_for("t4g.large") == "arm64" and sa.arch_for("t3.large") == "amd64"
    assert sa.arch_for("c7gn.large") == "arm64" and sa.arch_for("m7i.large") == "amd64"


# ------------------------------------------------------------------------------------------------
# network
# ------------------------------------------------------------------------------------------------
def test_security_group_created_with_80_443_only(aws: StubAws) -> None:
    st = aws.stub("ec2")
    st.add_response("describe_security_groups", {"SecurityGroups": []})
    st.add_response("create_security_group", {"GroupId": "sg-1"}, {
        "GroupName": sa.SG_NAME, "Description": ANY, "VpcId": "vpc-1", "TagSpecifications": ANY})
    st.add_response("authorize_security_group_ingress", {"Return": True},
                    {"GroupId": "sg-1", "IpPermissions": sa.desired_ingress(None)})
    assert sa.ensure_security_group(aws, "vpc-1", None) == "sg-1"
    aws.assert_done()


def test_security_group_drift_revokes_ssh(aws: StubAws) -> None:
    st = aws.stub("ec2")
    perms = [*sa.desired_ingress(None), {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                                         "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]
    st.add_response("describe_security_groups", {"SecurityGroups": [{"GroupId": "sg-1", "IpPermissions": perms}]})
    st.add_response("revoke_security_group_ingress", {"Return": True}, {"GroupId": "sg-1", "IpPermissions": [
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]})
    assert sa.ensure_security_group(aws, "vpc-1", None) == "sg-1"
    aws.assert_done()


def test_ssh_cidr_is_opt_in() -> None:
    assert all(r["FromPort"] != 22 for r in sa.desired_ingress(None))
    ssh = [r for r in sa.desired_ingress("198.51.100.7/32") if r["FromPort"] == 22]
    assert ssh[0]["IpRanges"][0]["CidrIp"] == "198.51.100.7/32" and "Ipv6Ranges" not in ssh[0]


def test_eip_reused_and_orphans_released(aws: StubAws) -> None:
    st = aws.stub("ec2")
    st.add_response("describe_addresses", {"Addresses": [
        {"AllocationId": "eipalloc-a", "PublicIp": "198.51.100.1", "InstanceId": "i-1", "AssociationId": "x"},
        {"AllocationId": "eipalloc-b", "PublicIp": "198.51.100.2"}]})
    st.add_response("release_address", {}, {"AllocationId": "eipalloc-b"})
    assert sa.ensure_eip(aws, "i-1") == ("eipalloc-a", "198.51.100.1")
    aws.assert_done()


def test_no_default_vpc_is_a_clear_error(aws: StubAws) -> None:
    aws.stub("ec2").add_response("describe_vpcs", {"Vpcs": []})
    with pytest.raises(sa.BootstrapError, match="create-default-vpc"):
        sa.default_subnet(aws, "t4g.large")


# ------------------------------------------------------------------------------------------------
# alarm / IAM documents / user-data
# ------------------------------------------------------------------------------------------------
def test_idle_alarm_is_60_min_cpu_below_5_with_stop_action() -> None:
    p = sa.idle_alarm_params("eu-south-1", "i-1")
    assert p["Threshold"] == 5.0 and p["ComparisonOperator"] == "LessThanThreshold"
    assert p["Period"] * p["EvaluationPeriods"] == 3600 and p["DatapointsToAlarm"] == p["EvaluationPeriods"]
    assert p["AlarmActions"] == ["arn:aws:automate:eu-south-1:ec2:stop"]
    assert p["Dimensions"] == [{"Name": "InstanceId", "Value": "i-1"}]


def test_pod_role_policy_scopes_stop_to_itself() -> None:
    doc = sa.pod_role_policy(ACCOUNT, "us-east-1", "i-abc")
    by_sid = {s["Sid"]: s for s in doc["Statement"]}
    assert by_sid["StopSelfOnly"]["Resource"] == f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-abc"
    assert by_sid["IdleAlarmToggle"]["Resource"].endswith(f"alarm:{sa.ALARM_NAME}")
    assert all(r.startswith(f"arn:aws:ssm:us-east-1:{ACCOUNT}:parameter/smartsched")
               for r in by_sid["ReadOwnParameters"]["Resource"])
    assert "github_token" not in json.dumps(by_sid["WriteGeneratedSecrets"])  # pod cannot overwrite the token
    assert "StopSelfOnly" not in json.dumps(sa.pod_role_policy(ACCOUNT, "us-east-1", None))


def test_user_data_renders_quoted_and_parses(tmp_path: Any) -> None:
    s = sa.Settings(region="eu-south-1", admin_email="a'b@example.org")
    text = sa.render_user_data(s, "203-0-113-10.sslip.io")
    assert "@@" not in text and len(text.encode()) < 16 * 1024
    assert "export SMARTSCHED_ADMIN_EMAIL='a'\"'\"'b@example.org'" in text
    f = tmp_path / "ud.sh"
    f.write_text(text)
    subprocess.run(["bash", "-n", str(f)], check=True)


def test_plan_is_offline() -> None:
    plan = sa.cmd_plan(sa.Settings(region="eu-central-1"))
    assert plan["resources"]["instance"]["arch"] == "arm64"
    assert plan["resources"]["budget"]["BudgetName"] == "smartsched-monthly-100usd"
    assert plan["panel_url_example"] == "https://203-0-113-10.sslip.io"


# ------------------------------------------------------------------------------------------------
# budget
# ------------------------------------------------------------------------------------------------
def test_existing_budget_is_reused_not_recreated(aws: StubAws) -> None:
    st = aws.stub("budgets")
    st.add_response("describe_budget", {"Budget": {**sa.budget_definition(100.0)}},
                    {"AccountId": ACCOUNT, "BudgetName": "smartsched-monthly-100usd"})
    st.add_response("describe_notifications_for_budget", {"Notifications": notifications()[:3]})
    for _ in range(3):
        st.add_response("describe_subscribers_for_notification",
                        {"Subscribers": SUBS})
    # only the missing FORECASTED 100 % alert is added
    st.add_response("create_notification", {}, {"AccountId": ACCOUNT, "BudgetName": sa.BUDGET_NAME,
                                                "Notification": notifications()[3], "Subscribers": ANY})
    sa.ensure_budget(aws, ACCOUNT, sa.Settings())
    aws.assert_done()
    assert ("budgets", "CreateBudget") not in aws.calls


def test_budget_created_only_when_missing(aws: StubAws) -> None:
    st = aws.stub("budgets")
    st.add_client_error("describe_budget", service_error_code="NotFoundException")
    st.add_response("create_budget", {}, {"AccountId": ACCOUNT, "Budget": sa.budget_definition(100.0),
                                          "NotificationsWithSubscribers": ANY, "ResourceTags": ANY})
    sa.ensure_budget(aws, ACCOUNT, sa.Settings())
    aws.assert_done()


def test_budget_alert_thresholds() -> None:
    got = {(n["NotificationType"], n["Threshold"]) for n in sa.budget_notifications()}
    assert got == {("ACTUAL", 50.0), ("ACTUAL", 80.0), ("ACTUAL", 100.0), ("FORECASTED", 100.0)}


def test_budget_action_updated_for_new_instance(aws: StubAws) -> None:
    st = aws.stub("budgets")
    old = {"ActionId": ACTION_ID, "BudgetName": sa.BUDGET_NAME, "NotificationType": "ACTUAL",
           "ActionType": "RUN_SSM_DOCUMENTS", "ActionThreshold": {"ActionThresholdValue": 100.0,
                                                                  "ActionThresholdType": "PERCENTAGE"},
           "Definition": sa.budget_action_definition("us-east-1", "i-old"), "ExecutionRoleArn": ROLE_ARN,
           "ApprovalModel": "AUTOMATIC", "Status": "STANDBY",
           "Subscribers": SUBS}
    st.add_response("describe_budget_actions_for_budget", {"Actions": [old]})
    st.add_response("update_budget_action", {"AccountId": ACCOUNT, "BudgetName": sa.BUDGET_NAME,
                                             "OldAction": old, "NewAction": old},
                    {"AccountId": ACCOUNT, "BudgetName": sa.BUDGET_NAME, "ActionId": ACTION_ID,
                     "NotificationType": "ACTUAL", "ActionThreshold": ANY, "ExecutionRoleArn": ROLE_ARN,
                     "ApprovalModel": "AUTOMATIC", "Subscribers": ANY,
                     "Definition": sa.budget_action_definition("us-east-1", "i-new")})
    assert sa.ensure_budget_action(aws, ACCOUNT, sa.Settings(), ROLE_ARN, "i-new") == ACTION_ID
    aws.assert_done()


# ------------------------------------------------------------------------------------------------
# full flows
# ------------------------------------------------------------------------------------------------
def stub_fresh_up(aws: StubAws) -> None:
    iam, ec2, ssm = aws.stub("iam"), aws.stub("ec2"), aws.stub("ssm")
    cw, budgets, pricing = aws.stub("cloudwatch"), aws.stub("budgets"), aws.stub("pricing")
    # pod role + profile
    iam.add_client_error("get_role", service_error_code="NoSuchEntity", http_status_code=404)
    iam.add_response("create_role", {"Role": role(sa.ROLE_NAME)})
    iam.add_response("list_attached_role_policies", {"AttachedPolicies": []})
    for arn in sa.POD_MANAGED_POLICIES:
        iam.add_response("attach_role_policy", {}, {"RoleName": sa.ROLE_NAME, "PolicyArn": arn})
    iam.add_response("put_role_policy", {})
    iam.add_client_error("get_instance_profile", service_error_code="NoSuchEntity", http_status_code=404)
    iam.add_response("create_instance_profile", {"InstanceProfile": profile(False)})
    iam.add_response("add_role_to_instance_profile", {})
    # network
    ec2.add_response("describe_vpcs", {"Vpcs": [{"VpcId": "vpc-1", "IsDefault": True}]})
    ec2.add_response("describe_instance_type_offerings", {"InstanceTypeOfferings": [
        {"InstanceType": "t4g.large", "LocationType": "availability-zone", "Location": "us-east-1b"}]})
    ec2.add_response("describe_subnets", {"Subnets": [
        {"SubnetId": "subnet-a", "AvailabilityZone": "us-east-1a"},
        {"SubnetId": "subnet-b", "AvailabilityZone": "us-east-1b"}]})
    ec2.add_response("describe_security_groups", {"SecurityGroups": []})
    ec2.add_response("create_security_group", {"GroupId": "sg-1"})
    ec2.add_response("authorize_security_group_ingress", {"Return": True})
    ec2.add_response("describe_instances", {"Reservations": []})
    ec2.add_response("describe_addresses", {"Addresses": []})
    ec2.add_response("allocate_address", {"AllocationId": "eipalloc-1", "PublicIp": "203.0.113.10"})
    # launch
    ssm.add_response("get_parameter", {"Parameter": {"Name": "ami", "Value": "ami-0abc"}})
    ec2.add_response("describe_images", {"Images": [{"ImageId": "ami-0abc", "RootDeviceName": "/dev/sda1"}]})
    ec2.add_response("run_instances", {"Instances": [instance("pending")]}, {
        "ImageId": "ami-0abc", "InstanceType": "t4g.large", "MinCount": 1, "MaxCount": 1, "SubnetId": "subnet-b",
        "SecurityGroupIds": ["sg-1"], "IamInstanceProfile": {"Name": sa.PROFILE_NAME}, "UserData": ANY,
        "BlockDeviceMappings": [{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 40, "VolumeType": "gp3",
                                                                   "DeleteOnTermination": True, "Encrypted": True}}],
        "MetadataOptions": {"HttpTokens": "required", "HttpPutResponseHopLimit": 1, "HttpEndpoint": "enabled"},
        "InstanceInitiatedShutdownBehavior": "stop", "TagSpecifications": ANY,
        "CreditSpecification": {"CpuCredits": "standard"}})
    ec2.add_client_error("describe_instances", service_error_code="InvalidInstanceID.NotFound")
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("running")]}]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "eipalloc-1", "PublicIp": "203.0.113.10"}]})
    ec2.add_response("associate_address", {"AssociationId": "eipassoc-1"},
                     {"AllocationId": "eipalloc-1", "InstanceId": "i-0123456789abcdef0", "AllowReassociation": True})
    # pod role again: now with StopInstances on the instance itself
    iam.add_response("get_role", {"Role": role(sa.ROLE_NAME)})
    iam.add_response("update_assume_role_policy", {})
    iam.add_response("list_attached_role_policies", {"AttachedPolicies": [
        {"PolicyName": a.rsplit("/", 1)[1], "PolicyArn": a} for a in sa.POD_MANAGED_POLICIES]})
    iam.add_response("put_role_policy", {}, {"RoleName": sa.ROLE_NAME, "PolicyName": sa.POD_POLICY_NAME,
                                             "PolicyDocument": json.dumps(sa.pod_role_policy(
                                                 ACCOUNT, "us-east-1", "i-0123456789abcdef0"))})
    iam.add_response("get_instance_profile", {"InstanceProfile": profile(True)})
    cw.add_response("put_metric_alarm", {}, sa.idle_alarm_params("us-east-1", "i-0123456789abcdef0"))
    # existing budget (aws-oidc-bootstrap.yml) with all four alerts
    budgets.add_response("describe_budget", {"Budget": sa.budget_definition(100.0)})
    budgets.add_response("describe_notifications_for_budget", {"Notifications": notifications()})
    for _ in range(4):
        budgets.add_response("describe_subscribers_for_notification",
                             {"Subscribers": SUBS})
    iam.add_client_error("get_role", service_error_code="NoSuchEntity", http_status_code=404)
    iam.add_response("create_role", {"Role": role(sa.BUDGET_ROLE_NAME)})
    iam.add_response("list_attached_role_policies", {"AttachedPolicies": []})
    iam.add_response("attach_role_policy", {}, {"RoleName": sa.BUDGET_ROLE_NAME,
                                                "PolicyArn": sa.BUDGET_ACTION_MANAGED_POLICY})
    budgets.add_response("describe_budget_actions_for_budget", {"Actions": []})
    budgets.add_response("create_budget_action", {"AccountId": ACCOUNT, "BudgetName": sa.BUDGET_NAME,
                                                  "ActionId": ACTION_ID}, {
        "AccountId": ACCOUNT, "BudgetName": sa.BUDGET_NAME, "NotificationType": "ACTUAL",
        "ActionType": "RUN_SSM_DOCUMENTS",
        "ActionThreshold": {"ActionThresholdValue": 100.0, "ActionThresholdType": "PERCENTAGE"},
        "Definition": sa.budget_action_definition("us-east-1", "i-0123456789abcdef0"),
        "ExecutionRoleArn": f"arn:aws:iam::{ACCOUNT}:role/{sa.BUDGET_ROLE_NAME}", "ApprovalModel": "AUTOMATIC",
        "Subscribers": SUBS, "ResourceTags": ANY})
    ssm.add_response("put_parameter", {"Version": 1}, {"Name": "/smartsched/panel_url",
                                                       "Value": "https://203-0-113-10.sslip.io", "Type": "String",
                                                       "Tags": ANY})
    pricing.add_response("get_products", {"PriceList": [price_item("0.0672")]})
    pricing.add_response("get_products", {"PriceList": [price_item("0.08")]})


def test_up_on_fresh_account(aws: StubAws) -> None:
    stub_fresh_up(aws)
    res = sa.cmd_up(aws, sa.Settings(), ACCOUNT, sleep=lambda _: None)
    aws.assert_done()
    assert res.panel_url == "https://203-0-113-10.sslip.io"
    assert res.instance_id == "i-0123456789abcdef0"
    assert res.estimate["total"] == pytest.approx(56.61)
    out = res.as_dict()
    assert "--with-decryption" in out["read_admin_password"]
    assert out["parameters"]["admin_password"] == "/smartsched/admin_password"


def test_up_actions_are_allowed_by_policies(aws: StubAws, bootstrap_policy: dict[str, Any]) -> None:
    stub_fresh_up(aws)
    sa.cmd_up(aws, sa.Settings(), ACCOUNT, sleep=lambda _: None)
    for action in sorted(aws.iam_actions()):
        assert matches(action, bootstrap_policy), f"{action} missing from iam/bootstrap-policy.json"
        assert matches(action, EXISTING_ROLE_POLICY), f"{action} not granted to smartsched-github-bootstrap"


def test_up_reuses_running_instance(aws: StubAws) -> None:
    """Second run (e.g. after renewing credentials): nothing is launched or allocated again."""
    iam, ec2 = aws.stub("iam"), aws.stub("ec2")
    for _ in range(2):
        iam.add_response("get_role", {"Role": role(sa.ROLE_NAME)})
        iam.add_response("update_assume_role_policy", {})
        iam.add_response("list_attached_role_policies", {"AttachedPolicies": [
            {"PolicyName": "p", "PolicyArn": a} for a in sa.POD_MANAGED_POLICIES]})
        iam.add_response("put_role_policy", {})
        iam.add_response("get_instance_profile", {"InstanceProfile": profile(True)})
        if _ == 0:
            ec2.add_response("describe_vpcs", {"Vpcs": [{"VpcId": "vpc-1"}]})
            ec2.add_response("describe_instance_type_offerings", {"InstanceTypeOfferings": [
                {"Location": "us-east-1a"}]})
            ec2.add_response("describe_subnets", {"Subnets": [{"SubnetId": "subnet-a",
                                                               "AvailabilityZone": "us-east-1a"}]})
            ec2.add_response("describe_security_groups", {"SecurityGroups": [
                {"GroupId": "sg-1", "IpPermissions": sa.desired_ingress(None)}]})
            ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance()]}]})
            ec2.add_response("describe_addresses", {"Addresses": [
                {"AllocationId": "eipalloc-1", "PublicIp": "203.0.113.10", "InstanceId": instance()["InstanceId"],
                 "AssociationId": "a"}]})
            ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance()]}]})
            ec2.add_response("describe_addresses", {"Addresses": [
                {"AllocationId": "eipalloc-1", "PublicIp": "203.0.113.10", "InstanceId": instance()["InstanceId"]}]})
    aws.stub("cloudwatch").add_response("put_metric_alarm", {})
    b = aws.stub("budgets")
    b.add_response("describe_budget", {"Budget": sa.budget_definition(100.0)})
    b.add_response("describe_notifications_for_budget", {"Notifications": notifications()})
    for _ in range(4):
        b.add_response("describe_subscribers_for_notification",
                       {"Subscribers": SUBS})
    iam.add_response("get_role", {"Role": role(sa.BUDGET_ROLE_NAME)})
    iam.add_response("update_assume_role_policy", {})
    iam.add_response("list_attached_role_policies", {"AttachedPolicies": [
        {"PolicyName": "p", "PolicyArn": sa.BUDGET_ACTION_MANAGED_POLICY}]})
    action = {"ActionId": ACTION_ID, "BudgetName": sa.BUDGET_NAME, "NotificationType": "ACTUAL",
              "ActionType": "RUN_SSM_DOCUMENTS",
              "ActionThreshold": {"ActionThresholdValue": 100.0, "ActionThresholdType": "PERCENTAGE"},
              "Definition": sa.budget_action_definition("us-east-1", instance()["InstanceId"]),
              "ExecutionRoleArn": f"arn:aws:iam::{ACCOUNT}:role/{sa.BUDGET_ROLE_NAME}",
              "ApprovalModel": "AUTOMATIC", "Status": "STANDBY",
              "Subscribers": SUBS}
    b.add_response("describe_budget_actions_for_budget", {"Actions": [action]})
    ssm = aws.stub("ssm")
    ssm.add_client_error("put_parameter", service_error_code="ParameterAlreadyExists")
    ssm.add_response("put_parameter", {"Version": 2}, {"Name": "/smartsched/panel_url", "Type": "String",
                                                       "Value": "https://203-0-113-10.sslip.io", "Overwrite": True})
    p = aws.stub("pricing")
    p.add_response("get_products", {"PriceList": [price_item("0.0672")]})
    p.add_response("get_products", {"PriceList": [price_item("0.08")]})
    res = sa.cmd_up(aws, sa.Settings(), ACCOUNT, sleep=lambda _: None)
    aws.assert_done()
    assert res.instance_id == instance()["InstanceId"]
    for op in ("RunInstances", "AllocateAddress", "CreateSecurityGroup", "CreateBudget", "CreateBudgetAction",
               "AssociateAddress"):
        assert ("ec2", op) not in aws.calls and ("budgets", op) not in aws.calls


def test_two_tagged_instances_refuse(aws: StubAws) -> None:
    iam, ec2 = aws.stub("iam"), aws.stub("ec2")
    iam.add_response("get_role", {"Role": role(sa.ROLE_NAME)})
    iam.add_response("update_assume_role_policy", {})
    iam.add_response("list_attached_role_policies", {"AttachedPolicies": [
        {"PolicyName": "p", "PolicyArn": a} for a in sa.POD_MANAGED_POLICIES]})
    iam.add_response("put_role_policy", {})
    iam.add_response("get_instance_profile", {"InstanceProfile": profile(True)})
    ec2.add_response("describe_vpcs", {"Vpcs": [{"VpcId": "vpc-1"}]})
    ec2.add_response("describe_instance_type_offerings", {"InstanceTypeOfferings": [{"Location": "us-east-1a"}]})
    ec2.add_response("describe_subnets", {"Subnets": [{"SubnetId": "s", "AvailabilityZone": "us-east-1a"}]})
    ec2.add_response("describe_security_groups", {"SecurityGroups": [
        {"GroupId": "sg-1", "IpPermissions": sa.desired_ingress(None)}]})
    two = [instance(iid="i-1"), instance(iid="i-2")]
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": two}]})
    with pytest.raises(sa.BootstrapError, match="2 tagged instances"):
        sa.cmd_up(aws, sa.Settings(), ACCOUNT, sleep=lambda _: None)


def test_status_reports_cost_and_orphans(aws: StubAws) -> None:
    ec2, cw, b, p = aws.stub("ec2"), aws.stub("cloudwatch"), aws.stub("budgets"), aws.stub("pricing")
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    p.add_response("get_products", {"PriceList": [price_item("0.0672")]})
    p.add_response("get_products", {"PriceList": [price_item("0.08")]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "e", "PublicIp": "203.0.113.10",
                                                           "InstanceId": "i-0123456789abcdef0"}]})
    cw.add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": sa.ALARM_NAME, "StateValue": "OK",
                                                          "ActionsEnabled": True}]})
    b.add_response("describe_budget", {"Budget": {**sa.budget_definition(100.0), "CalculatedSpend": {
        "ActualSpend": {"Amount": "12.5", "Unit": "USD"}, "ForecastedSpend": {"Amount": "40", "Unit": "USD"}}}})
    ec2.add_response("describe_volumes", {"Volumes": [{"VolumeId": "vol-orphan"}]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "e", "PublicIp": "203.0.113.10",
                                                           "AssociationId": "a"}]})
    for region in ("eu-central-1", "eu-south-1"):
        aws.stub("ec2", region).add_response("describe_instances", {"Reservations": []})
    out = sa.cmd_status(aws, sa.Settings(), ACCOUNT)
    aws.assert_done()
    assert out["panel_url"] == "https://203-0-113-10.sslip.io"
    assert out["budget"] == {"limit": "100.00", "actual": "12.5", "forecast": "40"}
    assert out["orphans"] == {"volumes": ["vol-orphan"], "eips": []}
    cur = out["estimated_monthly_usd"]["current_state"]
    assert cur["compute"] == 0 and cur["ebs_gp3"] == 3.2  # stopped: storage + IPv4 only
    assert out["estimated_monthly_usd"]["if_running_24x7"]["compute"] == 49.06


def test_status_skips_opt_in_region_that_is_not_enabled(aws: StubAws) -> None:
    """eu-south-1 is opt-in: when it is not enabled, EC2 answers AuthFailure; status must still succeed."""
    ec2, cw, b, p = aws.stub("ec2"), aws.stub("cloudwatch"), aws.stub("budgets"), aws.stub("pricing")
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    p.add_response("get_products", {"PriceList": [price_item("0.0672")]})
    p.add_response("get_products", {"PriceList": [price_item("0.08")]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "e", "PublicIp": "203.0.113.10",
                                                           "InstanceId": "i-0123456789abcdef0"}]})
    cw.add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": sa.ALARM_NAME, "StateValue": "OK",
                                                          "ActionsEnabled": True}]})
    b.add_response("describe_budget", {"Budget": {**sa.budget_definition(100.0), "CalculatedSpend": {
        "ActualSpend": {"Amount": "12.5", "Unit": "USD"}, "ForecastedSpend": {"Amount": "40", "Unit": "USD"}}}})
    ec2.add_response("describe_volumes", {"Volumes": [{"VolumeId": "vol-orphan"}]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "e", "PublicIp": "203.0.113.10",
                                                           "AssociationId": "a"}]})
    aws.stub("ec2", "eu-central-1").add_response("describe_instances", {"Reservations": []})
    aws.stub("ec2", "eu-south-1").add_client_error("describe_instances", service_error_code="AuthFailure",
                                                   service_message="not able to validate credentials")
    out = sa.cmd_status(aws, sa.Settings(), ACCOUNT)
    aws.assert_done()
    assert out["panel_url"] == "https://203-0-113-10.sslip.io"
    assert "eu-central-1" not in out["tagged_instances_in_other_regions"]
    assert "AuthFailure" in out["tagged_instances_in_other_regions"]["eu-south-1"]



def stub_down_region(aws: StubAws, region: str, with_resources: bool) -> None:
    ec2, cw, ssm = aws.stub("ec2", region), aws.stub("cloudwatch", region), aws.stub("ssm", region)
    if not with_resources:
        cw.add_response("describe_alarms", {"MetricAlarms": []})
        ec2.add_response("describe_instances", {"Reservations": []})
        ec2.add_response("describe_addresses", {"Addresses": []})
        ec2.add_response("describe_volumes", {"Volumes": []})
        ec2.add_response("describe_security_groups", {"SecurityGroups": []})
        ssm.add_response("get_parameters_by_path", {"Parameters": []})
        return
    cw.add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": sa.ALARM_NAME}]})
    cw.add_response("delete_alarms", {}, {"AlarmNames": [sa.ALARM_NAME]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance()]}]})
    ec2.add_response("terminate_instances", {"TerminatingInstances": []}, {"InstanceIds": ["i-0123456789abcdef0"]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("terminated")]}]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "e1", "PublicIp": "203.0.113.10",
                                                           "AssociationId": "as1"}]})
    ec2.add_response("disassociate_address", {}, {"AssociationId": "as1"})
    ec2.add_response("release_address", {}, {"AllocationId": "e1"})
    ec2.add_response("describe_volumes", {"Volumes": [{"VolumeId": "vol-1"}]})
    ec2.add_response("delete_volume", {}, {"VolumeId": "vol-1"})
    ec2.add_response("describe_security_groups", {"SecurityGroups": [{"GroupId": "sg-1"}]})
    ec2.add_client_error("delete_security_group", service_error_code="DependencyViolation")
    ec2.add_response("delete_security_group", {}, {"GroupId": "sg-1"})
    ssm.add_response("get_parameters_by_path", {"Parameters": [{"Name": f"/smartsched/p{i}"} for i in range(12)]})
    ssm.add_response("delete_parameters", {"DeletedParameters": ["x"]},
                     {"Names": sorted(f"/smartsched/p{i}" for i in range(12))[:10]})
    ssm.add_response("delete_parameters", {"DeletedParameters": ["x"]},
                     {"Names": sorted(f"/smartsched/p{i}" for i in range(12))[10:]})


def test_down_deletes_everything_tagged_but_keeps_budget(aws: StubAws, bootstrap_policy: dict[str, Any]) -> None:
    b, iam = aws.stub("budgets"), aws.stub("iam")
    b.add_response("describe_budget_actions_for_budget", {"Actions": [{
        "ActionId": ACTION_ID, "BudgetName": sa.BUDGET_NAME, "NotificationType": "ACTUAL",
        "ActionType": "RUN_SSM_DOCUMENTS", "ActionThreshold": {"ActionThresholdValue": 100.0,
                                                               "ActionThresholdType": "PERCENTAGE"},
        "Definition": sa.budget_action_definition("us-east-1", "i-1"), "ExecutionRoleArn": ROLE_ARN,
        "ApprovalModel": "AUTOMATIC", "Status": "STANDBY", "Subscribers": SUBS}]})
    b.add_response("delete_budget_action", {"AccountId": ACCOUNT, "BudgetName": sa.BUDGET_NAME, "Action": {
        "ActionId": ACTION_ID, "BudgetName": sa.BUDGET_NAME, "NotificationType": "ACTUAL",
        "ActionType": "RUN_SSM_DOCUMENTS", "ActionThreshold": {"ActionThresholdValue": 100.0,
                                                               "ActionThresholdType": "PERCENTAGE"},
        "Definition": {}, "ExecutionRoleArn": ROLE_ARN, "ApprovalModel": "AUTOMATIC", "Status": "STANDBY",
        "Subscribers": SUBS}})
    stub_down_region(aws, "us-east-1", True)
    stub_down_region(aws, "eu-central-1", False)
    stub_down_region(aws, "eu-south-1", False)
    iam.add_response("get_instance_profile", {"InstanceProfile": profile(True)})
    iam.add_response("remove_role_from_instance_profile", {})
    iam.add_response("delete_instance_profile", {})
    for name, inline, managed in ((sa.ROLE_NAME, [sa.POD_POLICY_NAME], list(sa.POD_MANAGED_POLICIES)),
                                  (sa.BUDGET_ROLE_NAME, [], [sa.BUDGET_ACTION_MANAGED_POLICY])):
        iam.add_response("get_role", {"Role": role(name)})
        iam.add_response("list_role_policies", {"PolicyNames": inline})
        for pname in inline:
            iam.add_response("delete_role_policy", {}, {"RoleName": name, "PolicyName": pname})
        iam.add_response("list_attached_role_policies", {"AttachedPolicies": [
            {"PolicyName": "p", "PolicyArn": a} for a in managed]})
        for a in managed:
            iam.add_response("detach_role_policy", {}, {"RoleName": name, "PolicyArn": a})
        iam.add_response("delete_role", {}, {"RoleName": name})
    aws.stub("resourcegroupstaggingapi", "us-east-1").add_response("get_resources", {"ResourceTagMappingList": [
        {"ResourceARN": "arn:aws:ec2:us-east-1:1:instance/i-1"}]})
    aws.stub("resourcegroupstaggingapi", "eu-central-1").add_client_error("get_resources",
                                                                          service_error_code="AccessDeniedException")
    aws.stub("resourcegroupstaggingapi", "eu-south-1").add_response("get_resources", {"ResourceTagMappingList": []})
    out = sa.cmd_down(aws, ACCOUNT, ["us-east-1", *sa.PRICE_REGIONS], sleep=lambda _: None)
    aws.assert_done()
    assert out["budget"] == "kept (smartsched-monthly-100usd)"
    assert out["us-east-1"]["eips"] == ["203.0.113.10"] and out["us-east-1"]["volumes"] == ["vol-1"]
    assert len(out["us-east-1"]["parameters"]) == 12
    assert "us-east-1" not in out["leftovers"]  # terminated instances are ignored
    assert "not checked" in out["leftovers"]["eu-central-1"][0]
    assert ("budgets", "DeleteBudget") not in aws.calls
    for action in aws.iam_actions() - {"tag:GetResources"}:
        assert matches(action, EXISTING_ROLE_POLICY), action
    for action in aws.iam_actions():
        assert matches(action, bootstrap_policy), action


def test_stop_and_start(aws: StubAws) -> None:
    ec2 = aws.stub("ec2")
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance()]}]})
    ec2.add_response("stop_instances", {"StoppingInstances": []}, {"InstanceIds": ["i-0123456789abcdef0"]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    assert sa.cmd_stop(aws, sleep=lambda _: None) == ["i-0123456789abcdef0"]
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    ec2.add_response("start_instances", {"StartingInstances": []}, {"InstanceIds": ["i-0123456789abcdef0"]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("running")]}]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "e", "PublicIp": "203.0.113.10",
                                                           "InstanceId": "i-0123456789abcdef0"}]})
    assert sa.cmd_start(aws, sleep=lambda _: None) == ["i-0123456789abcdef0"]
    aws.assert_done()


def test_policy_files_are_valid_json() -> None:
    iam_dir = sa.HERE / "iam"
    for f in iam_dir.glob("*.json"):
        doc = json.loads(f.read_text())
        assert doc["Version"] == "2012-10-17", f


def test_filter_console_keeps_boot_lines_and_redacts_credentials() -> None:
    text = "\n".join([
        "[    1.0] kernel noise",
        "[user-data] start 2026-10-08T11:44:00Z",
        "[pod-bootstrap] ADMIN_PASSWORD=hunter2-very-secret",
        "[pod-bootstrap] using token ghp_abcdefghijklmnopqrstuvwxyz0123",
        "Get:1 http://ports.ubuntu.com noble InRelease",
        "[pod-ci] key sk-ant-api03-abcdefghijkl stored",
        "cloud-init[1234]: Cloud-init v. 25.1 finished at Thu, 08 Oct 2026",
    ])
    lines = sa.filter_console(text)
    assert lines[0] == "[user-data] start 2026-10-08T11:44:00Z"
    assert len(lines) == 5
    joined = "\n".join(lines)
    for leaked in ("hunter2", "ghp_abcdef", "sk-ant-api03"):
        assert leaked not in joined
    assert "[redacted]" in lines[1] and "[redacted]" in lines[2] and "[redacted]" in lines[3]


def test_logs_reads_latest_console_output(aws: StubAws) -> None:
    import base64

    ec2 = aws.stub("ec2")
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("running")]}]})
    out_text = "noise\n[user-data] waiting for SSM /smartsched/github_token\n"
    ec2.add_response("get_console_output", {"InstanceId": "i-0123456789abcdef0",
                                            "Output": base64.b64encode(out_text.encode()).decode()},
                     {"InstanceId": "i-0123456789abcdef0", "Latest": True})
    ssm = aws.stub("ssm")
    ssm.add_response("send_command", {"Command": {"CommandId": "0b7a3c1e-1f2d-4e5a-9b8c-7d6e5f4a3b21"}})
    ssm.add_client_error("get_command_invocation", service_error_code="InvocationDoesNotExist")
    ssm.add_response("get_command_invocation", {"Status": "Success", "StandardOutputContent":
                                                "smartsched-backend Up 2 minutes (healthy)\n"
                                                "pod-ci: ADMIN_PASSWORD=hunter2-secret\n",
                                                "StandardErrorContent": ""})
    out = sa.cmd_logs(aws, sleep=lambda _s: None)
    aws.assert_done()
    pod = out["i-0123456789abcdef0"]
    assert pod["lines"] == ["[user-data] waiting for SSM /smartsched/github_token"]
    assert pod["runtime"][0] == "smartsched-backend Up 2 minutes (healthy)"
    assert "hunter2" not in "\n".join(pod["runtime"])


def test_pod_diag_prints_failed_gate_tails(tmp_path: Any) -> None:
    """POD_DIAG's python block: the last FAILED_GATE_TAIL lines of each failed gate of the newest finished run."""
    import sqlite3
    import sys

    logs = tmp_path / "logs"
    db = sqlite3.connect(tmp_path / "ci.sqlite3")
    db.executescript("""
        CREATE TABLE runs (id INTEGER PRIMARY KEY, branch TEXT, sha TEXT, state TEXT, finished_at REAL);
        CREATE TABLE steps (run_id INTEGER, seq INTEGER, name TEXT, state TEXT, exit_code INTEGER, log_path TEXT);
    """)

    def gate_log(run: int, name: str, lines: list[str]) -> str:
        (logs / str(run)).mkdir(parents=True, exist_ok=True)
        path = logs / str(run) / f"{name}.log"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    backend = [f"backend line {i}" for i in range(100)] + ["FAILED tests/test_x.py::test_y - assert 1 == 2"]
    db.executemany("INSERT INTO runs VALUES (?, ?, ?, ?, ?)", [
        (80, "main", "a" * 40, "failure", 100.0),
        (81, "claude/x", "e92feedb" + "0" * 32, "failure", 200.0),
        (82, "claude/x", "f" * 40, "running", None),  # still running: not the newest *finished* run
    ])
    db.executemany("INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?)", [
        (80, 1, "infra", "failure", 1, gate_log(80, "infra", ["old run"])),
        (81, 1, "prepare", "success", 0, gate_log(81, "prepare", ["prepare ok"])),
        (81, 2, "backend", "failure", 1, gate_log(81, "backend", backend)),
        (81, 3, "frontend", "failure", -9, gate_log(81, "frontend", ["vitest", "[pod-ci] TIMEOUT after 1800 s"])),
        (81, 4, "e2e-real", "skipped", None, ""),
    ])
    db.commit()
    db.close()
    out = subprocess.run([sys.executable, "-", str(tmp_path), str(sa.FAILED_GATE_TAIL)], input=sa.POD_FAILED_GATES_PY,
                         text=True, capture_output=True, check=True).stdout.splitlines()
    assert out[0] == "==== newest finished run #81 claude/x@e92feedb: failure"
    i = out.index(f"==== backend: failure (exit 1) {logs / '81' / 'backend.log'}")
    assert out[i + 1:i + 1 + sa.FAILED_GATE_TAIL] == backend[-sa.FAILED_GATE_TAIL:]
    assert out[-3:] == [f"==== frontend: failure (exit -9) {logs / '81' / 'frontend.log'}", "vitest",
                        "[pod-ci] TIMEOUT after 1800 s"]
    assert "prepare ok" not in out and "old run" not in out and not any("e2e-real" in line for line in out)
    assert f"python3 - /var/lib/smartsched-ci {sa.FAILED_GATE_TAIL} <<" in sa.POD_DIAG
    assert sa.POD_FAILED_GATES_PY.strip() in sa.POD_DIAG
    # the important blocks first (SSM keeps the first ~24 000 chars): status, failed gates, then the rest
    assert sa.POD_DIAG.index("PODCI_STATUS") < sa.POD_DIAG.index("PODCI_PY") < sa.POD_DIAG.index("list-timers")
    assert "stat -c '%U %a %n' /opt/smartsched/src /opt/smartsched/src/.git" in sa.POD_DIAG


def status_db(tmp_path: Any, now: float) -> Any:
    import sqlite3

    db = sqlite3.connect(tmp_path / "ci.sqlite3")
    db.executescript("""
        CREATE TABLE runs (id INTEGER PRIMARY KEY, branch TEXT, sha TEXT, state TEXT, deploy INTEGER, attempts INTEGER,
            created_at REAL, started_at REAL, finished_at REAL, summary TEXT);
        CREATE TABLE steps (run_id INTEGER, seq INTEGER, name TEXT, state TEXT, blocking INTEGER, started_at REAL,
            finished_at REAL, exit_code INTEGER, log_path TEXT);
    """)
    return db


CONTEXT_MD = "\n".join([
    "# Test info", "", "- Name: bookings \u203a book a room", "", "# Error details", "",
    "Error: expect(locator).toHaveText(expected) failed",
    'Expected: "Deneme Kullanici Bir"  contact sample@example.test or 0555 123 45 67',
    "", "# Page snapshot", "", "```yaml",
    '- generic [ref=e1]:', '  - heading "Rezervasyonlar" [level=1] [ref=e2]',
    '  - row "Ornek Kisi 09:00 Oda 101" [ref=e3]:', '    - cell "Ornek Kisi" [ref=e4]',
    "    - text: Ornek Kisi token=abc123", '  - link "Panel" [ref=e5]:', "    - /url: /panel?user=7", "```",
]) + "\n"


def shard_log(n_ok: int, failing: list[str], total: int | None = None, details: bool = False) -> str:
    out = f"Running {total or n_ok + len(failing)} tests using 1 worker\n"
    out += "".join(f"  \u2713  {i} [chromium] \u203a e2e/a.spec.ts:1:1 \u203a ok (1.0s)\n" for i in range(1, n_ok + 1))
    out += "".join(f"  \u2718  {n_ok + i + 1} [chromium] \u203a {t} (9.0s)\n" for i, t in enumerate(failing))
    out += "".join(f"  \u2718  {n_ok + i + 1} [chromium] \u203a {t} (retry #1) (9.0s)\n" for i, t in enumerate(failing))
    if details:
        for i, t in enumerate(failing, 1):
            out += (f"\n  {i}) [chromium] \u203a {t} \n\n    Error: expect(locator).toBeVisible() failed\n\n"
                    f"    Locator: getByTestId('row-{i}')\n    Expected: visible\n"
                    "    Received: <element(s) not found>\n"
                    f"    Timeout: 10000ms\n\n      at {t.split(' ')[0]}:12:5\n")
        out += f"\n  {len(failing)} failed\n  {n_ok} passed (40.0m)\n"
    return out + "==== backend log (tail)\n" + "".join(f"backend noise {i}\n" for i in range(200))


def run_py(script: str, *args: str) -> str:
    import sys

    return subprocess.run([sys.executable, "-", *args], input=script, text=True, capture_output=True,
                          check=True).stdout


def test_pod_status_block_shows_runs_running_gates_shard_progress_and_live_failures(tmp_path: Any) -> None:
    import time

    now = time.time()
    db = status_db(tmp_path, now)
    logs = tmp_path / "logs"
    (logs / "91").mkdir(parents=True)
    live = logs / "91" / "e2e-real-2.log"
    live.write_text(shard_log(140, [f"e2e/b.spec.ts:1:1 \u203a bad {i}" for i in range(3)], total=150),
                    encoding="utf-8")
    failed_live = logs / "91" / "e2e-real-1.log"
    failed_live.write_text(shard_log(10, [f"e2e/c.spec.ts:2:1 \u203a broken {i}" for i in range(8)]),
                           encoding="utf-8")
    db.executemany("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (90, "claude/gracious-cerf-w1598m", "e" * 40, "failure", 1, 1, now - 7200, now - 7000, now - 3000,
         "failed: e2e-real-1"),
        (91, "claude/gracious-cerf-w1598m", "f" * 40, "running", 1, 1, now - 1500, now - 1400, None, ""),
    ])
    db.executemany("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?)", [
        (90, 0, "prepare", "success", 1, now - 7000, now - 6900, 0, ""),
        (90, 1, "e2e-real-1", "failure", 1, now - 6000, now - 3100, 1, ""),
        (91, 0, "prepare", "success", 1, now - 1400, now - 1300, 0, ""),
        (91, 1, "e2e-real-1", "failure", 1, now - 1300, now - 100, 1, str(failed_live)),
        (91, 2, "e2e-real-2", "running", 1, now - 1260, None, None, str(live)),
    ])
    db.commit()
    db.close()
    out = run_py(sa.POD_STATUS_PY, str(tmp_path))
    lines = out.splitlines()
    assert lines[0].startswith("==== pod-ci runs (newest 12)")
    assert lines[1].startswith("#91 ") and " running " in lines[1] and lines[2].startswith("#90 ")
    assert "failed: e2e-real-1" in lines[2] and "took 66m40s" in lines[2]
    assert any(line.startswith("==== RUNNING run #91") for line in lines)
    shard = next(line for line in lines if "e2e-real-2" in line and "shard" in line)
    assert "shard 2: 143/150 done, 3 failed" in shard and "21m" in shard
    # failures of the running run show before it ends: the failed gate's and the running shard's titles
    assert "bad 2 (9.0s)" in out and "broken 0 (9.0s)" in out and "broken 5 (9.0s)" in out
    assert "broken 6 (9.0s)" not in out and "... 2 more" in out  # at most 6 titles per gate
    assert "retry #1" not in out
    assert any(line.startswith("==== step durations of run #90") for line in lines)
    assert "error context" not in out  # that is the failed-gates block's, after every gate's failures


def test_failed_gates_block_gives_every_gate_its_failures_before_any_error_context(tmp_path: Any) -> None:
    """Run #141: 19 error-context files of shard 1 used to crowd out shards 2 and 3 and the infra tail."""
    import time

    now = time.time()
    db = status_db(tmp_path, now)
    logs = tmp_path / "logs" / "141"
    logs.mkdir(parents=True)
    paths = {}
    for i, n in ((1, 19), (2, 4), (3, 2)):
        paths[i] = logs / f"e2e-real-{i}.log"
        paths[i].write_text(shard_log(100, [f"e2e/s{i}-{k}.spec.ts:3:1 \u203a case {k}" for k in range(n)],
                                      details=True), encoding="utf-8")
    infra = logs / "infra.log"
    infra.write_text("".join(f"collect line {i}\n" for i in range(300))
                     + "FAILED infra/aws/tests/test_x.py::test_y - AssertionError\n1 failed, 319 passed in 28.4s\n",
                     encoding="utf-8")
    db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
               (141, "claude/gracious-cerf-w1598m", "1" * 40, "failure", 1, 1, now - 9000, now - 8900, now - 10,
                "failed: infra, e2e-real-1, e2e-real-2, e2e-real-3"))
    db.executemany("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?)", [
        (141, 0, "infra", "failure", 1, now - 8800, now - 8750, 1, str(infra)),
        *[(141, i, f"e2e-real-{i}", "failure", 1, now - 8000, now - 20, 1, str(paths[i])) for i in (1, 2, 3)],
    ])
    db.commit()
    db.close()
    for i, n in ((1, 19), (2, 4), (3, 2)):
        for k in range(n):
            d = tmp_path / "logs/141/artifacts" / f"e2e-shard-{i}" / f"s{i}-{k}-chromium"
            d.mkdir(parents=True)
            (d / "error-context.md").write_text(CONTEXT_MD, encoding="utf-8")
    out = run_py(sa.POD_FAILED_GATES_PY, str(tmp_path), str(sa.FAILED_GATE_TAIL))
    assert sa.FAILED_GATE_TAIL == 25
    first_ctx = out.index("==== error context of")
    gates_part = out[:first_ctx]
    # infra: the end of its log (the pytest summary), nothing older than the tail
    assert "1 failed, 319 passed in 28.4s" in gates_part and "collect line 299" in gates_part
    assert "collect line 270" not in gates_part
    for i in (1, 2, 3):
        section = gates_part[gates_part.index(f"==== e2e-real-{i}: failure"):]
        section = section[:section.index("\n==== ", 1) if "\n==== " in section[1:] else len(section)]
        body = section.splitlines()[1:]
        assert len(body) <= sa.FAILED_GATE_TAIL
        assert "case 0 (9.0s)" in section and "failed" in section  # titles + summary first
        titles_end = max(j for j, ln in enumerate(body) if "\u2718" in ln or ln.strip().endswith("failed"))
        assert any("Error: expect(locator)" in ln for ln in body[titles_end:])  # then the failure details
        assert "Received: <element(s) not found>" in section and "backend noise" not in section
        assert "Locator: getByTestId('row-1')" in section
    # then the error context, shared: every shard's files, at most 3 per gate, redacted
    ctx = out[first_ctx:]
    for i in (1, 2, 3):
        assert f"==== error context of e2e-real-{i}" in ctx
    assert ctx.count("-- e2e-shard-1/") == 3 and ctx.count("-- e2e-shard-3/") == 2
    for leaked in ("Ornek", "Kisi", "Deneme", "Kullanici", "sample@example.test", "0555 123 45 67", "abc123",
                   "user=7", "Rezervasyonlar"):
        assert leaked not in ctx, leaked
    assert '- heading "[text]" [level=1] [ref=e2]' in ctx and "[email]" in ctx and "# Error details" in ctx
    for block in ctx.split("\n-- ")[1:]:
        assert len([ln for ln in block.splitlines()[1:] if ln.startswith("  ")]) <= 10
    assert len(out) < 12_500  # the shell cap (head -c) never has to cut it
    assert "| head -c 12500" in sa.POD_DIAG and "| head -c 5000" in sa.POD_DIAG


def test_failed_gates_block_shows_backend_errors_per_shard_and_the_main_region_first(tmp_path: Any) -> None:
    import time

    now = time.time()
    db = status_db(tmp_path, now)
    logs = tmp_path / "logs" / "150"
    logs.mkdir(parents=True)
    shard = logs / "e2e-real-2.log"
    shard.write_text(shard_log(50, ["e2e/studio.spec.ts:9:1 \u203a scope sentence"], details=True), encoding="utf-8")
    db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
               (150, "claude/gracious-cerf-w1598m", "2" * 40, "failure", 1, 1, now - 900, now - 800, now - 5,
                "failed: e2e-real-2"))
    db.execute("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?)",
               (150, 3, "e2e-real-2", "failure", 1, now - 700, now - 10, 1, str(shard)))
    db.commit()
    db.close()
    art = tmp_path / "logs/150/artifacts"
    (art / "e2e-shard-2/studio-chromium").mkdir(parents=True)
    (art / "backend-errors-2.log").write_text("\n".join([
        'INFO: "GET /api/v1/studio/scope HTTP/1.1" 500 Internal Server Error',
        "Traceback (most recent call last):",
        "sqlite3.OperationalError: database is locked",
        "ERROR: request by Ornek Kisi failed",
        *[f"ERROR: extra line {i}" for i in range(40)],
    ]) + "\n", encoding="utf-8")
    (art / "e2e-shard-2/studio-chromium/error-context.md").write_text("\n".join([
        "# Page snapshot", "```yaml", "- generic [ref=e1]:", "  - navigation [ref=e2]:",
        '    - link "Sidebar Link" [ref=e3]', "  - main [ref=e9]:", '    - heading "Studio" [level=1] [ref=e10]',
        "    - text: Ornek Kisi", "```",
    ]) + "\n", encoding="utf-8")
    out = run_py(sa.POD_FAILED_GATES_PY, str(tmp_path), str(sa.FAILED_GATE_TAIL))
    gate = out[out.index("==== e2e-real-2: failure"):out.index("==== error context of")]
    assert gate.index("scope sentence") < gate.index("Error: expect(locator)") < gate.index("---- backend errors")
    backend = gate[gate.index("---- backend errors"):]
    # (capitalised word runs such as "Internal Server Error" fall to the name redaction too: redact more, not less)
    assert '/api/v1/studio/scope HTTP/1.1" 500' in backend and "database is locked" in backend
    assert "Ornek Kisi" not in backend and "[name]" in backend  # redacted like the other artifacts
    assert "extra line 15" in backend and "extra line 16" not in backend  # the first 20 lines
    ctx = out[out.index("==== error context of"):]
    assert "# Page snapshot (from the main region)" in ctx
    assert "navigation" not in ctx and "- main [ref=e9]" in ctx and '- heading "[text]" [level=1] [ref=e10]' in ctx
    assert "Ornek" not in ctx and "Sidebar" not in ctx


def test_resize_stops_changes_the_type_and_starts_without_touching_the_budget(aws: StubAws) -> None:
    ec2 = aws.stub("ec2")
    iid = "i-0123456789abcdef0"
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("running")]}]})
    ec2.add_response("stop_instances", {"StoppingInstances": []}, {"InstanceIds": [iid]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    ec2.add_response("modify_instance_attribute", {},
                     {"InstanceId": iid, "InstanceType": {"Value": "c7g.4xlarge"}})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("stopped")]}]})
    ec2.add_response("start_instances", {"StartingInstances": []}, {"InstanceIds": [iid]})
    ec2.add_response("describe_instances", {"Reservations": [{"Instances": [instance("running")]}]})
    ec2.add_response("describe_addresses", {"Addresses": [{"AllocationId": "e", "PublicIp": "203.0.113.10",
                                                           "InstanceId": iid}]})
    s = sa.Settings(instance_type="c7g.4xlarge", budget_usd=450.0)
    out = sa.cmd_resize(aws, s, "123456789012", sleep=lambda _: None)
    assert out["from"] == "t4g.large" and out["to"] == "c7g.4xlarge" and out["budget_usd"] is None
    ec2.assert_no_pending_responses()


def test_ci_upgrade_script_reinstalls_from_the_deploy_branch_and_restarts_the_worker() -> None:
    script = sa.pod_ci_upgrade_script(sa.Settings(deploy_branch="claude/gracious-cerf-w1598m"))
    lines = script.splitlines()
    assert lines[0] == "set -eu"  # /bin/sh on the pod (SSM): dash has no pipefail
    assert lines.index("systemctl stop smartsched-ci-update.path smartsched-ci-update.service || true") < \
        next(i for i, x in enumerate(lines) if "install.sh --upgrade" in x)
    assert "--branch claude/gracious-cerf-w1598m https://github.com/ArioMoniri/classroombookings.git" in script
    restart = "systemctl start --no-block smartsched-ci-worker.service"
    assert script.index("install.sh --upgrade") < script.index(restart)
