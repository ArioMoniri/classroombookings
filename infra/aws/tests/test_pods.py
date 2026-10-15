"""One pod per deploy branch (gracious = institution data, universal = empty): disjoint names, SSM prefixes, tags
and budgets, and neither pod's `down` touches the other's resources."""

from __future__ import annotations

import fnmatch
import json
from typing import Any

import pytest
from awsstub import StubAws

import smartsched_aws as sa

# The live first pod's names: changing them would orphan its resources.
LEGACY = {"INSTANCE_NAME": "smartsched-pod", "SG_NAME": "smartsched-pod-sg", "EIP_NAME": "smartsched-pod-eip",
          "ROLE_NAME": "smartsched-pod-role", "PROFILE_NAME": "smartsched-pod-profile",
          "POD_POLICY_NAME": "smartsched-pod", "BUDGET_ROLE_NAME": "smartsched-budget-action-role",
          "BUDGET_NAME": "smartsched-monthly-100usd", "ALARM_NAME": "smartsched-pod-idle-stop",
          "SSM_PREFIX": "/smartsched"}


def test_first_pod_keeps_its_names() -> None:
    assert sa.pod_names(sa.PODS["gracious"]) == LEGACY
    for k, v in LEGACY.items():
        assert getattr(sa, k) == v


def test_universal_names_are_disjoint_and_allowed_by_the_bootstrap_policy(bootstrap_policy: dict[str, Any]) -> None:
    u = sa.pod_names(sa.PODS["universal"])
    assert set(u.values()).isdisjoint(LEGACY.values())
    assert u["SSM_PREFIX"] == "/smartsched-universal"
    assert not u["SSM_PREFIX"].startswith(LEGACY["SSM_PREFIX"] + "/")  # gracious `down` lists /smartsched recursively
    resources = [r for st in bootstrap_policy["Statement"]
                 for r in (st["Resource"] if isinstance(st["Resource"], list) else [st["Resource"]])]

    def allowed(arn: str) -> bool:
        return any(fnmatch.fnmatchcase(arn, r) for r in resources)

    assert allowed(f"arn:aws:ssm:us-east-1:1:parameter{u['SSM_PREFIX']}/admin_password")
    assert allowed(f"arn:aws:iam::1:role/{u['ROLE_NAME']}") and allowed(f"arn:aws:iam::1:role/{u['BUDGET_ROLE_NAME']}")
    assert allowed(f"arn:aws:iam::1:instance-profile/{u['PROFILE_NAME']}")
    assert allowed(f"arn:aws:cloudwatch:us-east-1:1:alarm:{u['ALARM_NAME']}")
    assert allowed(f"arn:aws:budgets::1:budget/{u['BUDGET_NAME']}")
    # mutations are conditioned on Project=smartsched: every pod keeps that tag
    sa.use_pod(sa.PODS["universal"])
    assert {"Key": "Project", "Value": "smartsched"} in sa.tags("x")


def test_resolve_pod_by_name_or_branch() -> None:
    assert sa.resolve_pod(None).name == "gracious"
    assert sa.resolve_pod("universal") is sa.resolve_pod("claude/smartsched-universal")
    assert sa.resolve_pod("claude/gracious-cerf-w1598m").name == "gracious"
    with pytest.raises(sa.BootstrapError, match="unknown pod"):
        sa.resolve_pod("main")


def test_tags_filters_and_mine_per_pod() -> None:
    other = {"Tags": [{"Key": "Project", "Value": "smartsched"}, {"Key": "Pod", "Value": "universal"}]}
    legacy = {"Tags": [{"Key": "Project", "Value": "smartsched"}]}
    own = {"Tags": [{"Key": "Pod", "Value": "gracious"}]}
    assert {"Key": "Pod", "Value": "gracious"} in sa.tags("x")
    assert [f["Name"] for f in sa.tag_filter("n")] == ["tag:Project", "tag:Name"]  # legacy resources have no Pod
    assert sa.mine([other, legacy, own, {}]) == [legacy, own, {}]
    sa.use_pod(sa.PODS["universal"])
    assert {"Name": "tag:Pod", "Values": ["universal"]} in sa.tag_filter()
    assert sa.mine([other, own]) == [other]


def _down_region_stubs(aws: StubAws, pod: str, ssm_prefix: str, alarms: list[str], deleted: list[str]) -> None:
    ec2, cw, ssm = aws.stub("ec2"), aws.stub("cloudwatch"), aws.stub("ssm")
    filters = [{"Name": "tag:Project", "Values": ["smartsched"]}]
    if pod != "gracious":
        filters.append({"Name": "tag:Pod", "Values": [pod]})
    tagged = {"universal": [{"Key": "Pod", "Value": "universal"}],
              "legacy": [{"Key": "Project", "Value": "smartsched"}]}
    cw.add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": a} for a in alarms]},
                    {"AlarmNamePrefix": f"smartsched{sa.PODS[pod].suffix}-"})
    if deleted:
        cw.add_response("delete_alarms", {}, {"AlarmNames": deleted})
    other_inst = {"InstanceId": "i-universal", "Tags": tagged["universal"], "State": {"Name": "running"}}
    ec2.add_response("describe_instances",
        {"Reservations": [{"Instances": [other_inst]}]} if pod == "gracious" else {"Reservations": []},
        {"Filters": [*filters, {"Name": "instance-state-name",
                                "Values": ["pending", "running", "stopping", "stopped"]}]})
    ec2.add_response("describe_addresses", {"Addresses": [
        {"AllocationId": "e-u", "PublicIp": "203.0.113.20", "Tags": tagged["universal"]}]} if pod == "gracious"
        else {"Addresses": []}, {"Filters": filters})
    ec2.add_response("describe_volumes", {"Volumes": [{"VolumeId": "vol-u", "Tags": tagged["universal"]}]}
                     if pod == "gracious" else {"Volumes": []},
                     {"Filters": [*filters, {"Name": "status", "Values": ["available"]}]})
    ec2.add_response("describe_security_groups", {"SecurityGroups": [
        {"GroupId": "sg-legacy", "Tags": tagged["legacy"]}, {"GroupId": "sg-u", "Tags": tagged["universal"]}]}
        if pod == "gracious" else {"SecurityGroups": [{"GroupId": "sg-u", "Tags": tagged["universal"]}]},
        {"Filters": filters})
    ec2.add_response("delete_security_group", {}, {"GroupId": "sg-legacy" if pod == "gracious" else "sg-u"})
    ssm.add_response("get_parameters_by_path", {"Parameters": [{"Name": f"{ssm_prefix}/admin_password"}]},
                     {"Path": ssm_prefix, "Recursive": True, "WithDecryption": False, "MaxResults": 10})
    ssm.add_response("delete_parameters", {"DeletedParameters": ["x"]}, {"Names": [f"{ssm_prefix}/admin_password"]})


def test_gracious_down_leaves_the_universal_pod_alone(aws: StubAws) -> None:
    _down_region_stubs(aws, "gracious", "/smartsched",
                       alarms=["smartsched-pod-idle-stop", "smartsched-universal-pod-idle-stop"],
                       deleted=["smartsched-pod-idle-stop"])
    out = sa.down_region(aws, "us-east-1", sleep=lambda _: None)
    aws.assert_done()
    assert out["instances"] == [] and out["eips"] == [] and out["volumes"] == []
    assert out["security_groups"] == ["sg-legacy"] and out["alarms"] == ["smartsched-pod-idle-stop"]


def test_universal_down_is_scoped_by_its_pod_tag_and_prefix(aws: StubAws) -> None:
    sa.use_pod(sa.PODS["universal"])
    _down_region_stubs(aws, "universal", "/smartsched-universal", alarms=["smartsched-universal-pod-idle-stop"],
                       deleted=["smartsched-universal-pod-idle-stop"])
    out = sa.down_region(aws, "us-east-1", sleep=lambda _: None)
    aws.assert_done()
    assert out["security_groups"] == ["sg-u"] and out["parameters"] == ["/smartsched-universal/admin_password"]


def test_plan_and_user_data_for_the_universal_pod(capsys: Any) -> None:
    assert sa.main(["plan", "--pod", "universal", "--region", "eu-central-1"]) == 0
    plan = json.loads(capsys.readouterr().out)
    text = json.dumps(plan)
    assert "smartsched-universal-pod-role" in text and "smartsched-pod-role" not in text
    assert sa.main(["render-user-data", "--deploy-branch", "claude/smartsched-universal",
                    "--region", "eu-central-1"]) == 0
    ud = capsys.readouterr().out
    assert "SMARTSCHED_DEPLOY_BRANCH=claude/smartsched-universal" in ud
    assert "SMARTSCHED_SSM_PREFIX=/smartsched-universal" in ud
    assert "SMARTSCHED_CI_BRANCHES=claude/smartsched-universal\n" in ud
    sa.use_pod(sa.PODS["gracious"])
    assert sa.main(["render-user-data", "--region", "eu-central-1"]) == 0
    ud = capsys.readouterr().out
    assert "SMARTSCHED_DEPLOY_BRANCH=claude/gracious-cerf-w1598m" in ud and "SMARTSCHED_SSM_PREFIX=/smartsched\n" in ud
