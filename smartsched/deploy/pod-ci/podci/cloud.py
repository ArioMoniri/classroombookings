"""AWS from the pod (instance role via IMDSv2): SSM parameters, heartbeat metrics, idle alarm toggle,
self-stop. Disabled (NoCloud) with PODCI_CLOUD=0 for local runs and tests."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

IMDS = "http://169.254.169.254/latest"
NAMESPACE = "SmartSched/Pod"


def imds(path: str, timeout: float = 2) -> str:
    tok_req = urllib.request.Request(f"{IMDS}/api/token", method="PUT",  # noqa: S310 - link-local IMDS
                                     headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"})
    with urllib.request.urlopen(tok_req, timeout=timeout) as r:  # noqa: S310
        token = r.read().decode()
    req = urllib.request.Request(f"{IMDS}/{path}", headers={"X-aws-ec2-metadata-token": token})  # noqa: S310
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return str(r.read().decode())


class Cloud:
    def __init__(self, ssm_prefix: str, alarm_name: str, session: Any = None, instance_id: str | None = None,
                 region: str | None = None):
        self.ssm_prefix = ssm_prefix.rstrip("/")
        self.alarm_name = alarm_name
        self._session = session
        self._iid = instance_id
        self._region = region
        self._clients: dict[str, Any] = {}

    @property
    def instance_id(self) -> str:
        if self._iid is None:
            self._iid = imds("meta-data/instance-id")
        return self._iid

    @property
    def region(self) -> str:
        if self._region is None:
            self._region = str(json.loads(imds("dynamic/instance-identity/document"))["region"])
        return self._region

    def client(self, name: str) -> Any:
        if name not in self._clients:
            if self._session is None:
                import boto3

                self._session = boto3.session.Session(region_name=self.region)
            self._clients[name] = self._session.client(name)
        return self._clients[name]

    def get_param(self, name: str, decrypt: bool = True) -> str | None:
        try:
            resp = self.client("ssm").get_parameter(Name=f"{self.ssm_prefix}/{name}", WithDecryption=decrypt)
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") == "ParameterNotFound":
                return None
            raise
        return str(resp["Parameter"]["Value"])

    def put_param(self, name: str, value: str, secure: bool) -> None:
        ssm = self.client("ssm")
        full = f"{self.ssm_prefix}/{name}"
        kind = "SecureString" if secure else "String"
        try:
            ssm.put_parameter(Name=full, Value=value, Type=kind, Tags=[{"Key": "Project", "Value": "smartsched"}])
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") != "ParameterAlreadyExists":
                raise
            ssm.put_parameter(Name=full, Value=value, Type=kind, Overwrite=True)

    def heartbeat(self, ci_running: bool) -> None:
        dims = [{"Name": "InstanceId", "Value": self.instance_id}]
        self.client("cloudwatch").put_metric_data(Namespace=NAMESPACE, MetricData=[
            {"MetricName": "Heartbeat", "Dimensions": dims, "Value": 1.0, "Unit": "Count"},
            {"MetricName": "CIJobRunning", "Dimensions": dims, "Value": 1.0 if ci_running else 0.0, "Unit": "Count"},
        ])

    def set_alarm_actions(self, enabled: bool) -> None:
        cw = self.client("cloudwatch")
        if enabled:
            cw.enable_alarm_actions(AlarmNames=[self.alarm_name])
        else:
            cw.disable_alarm_actions(AlarmNames=[self.alarm_name])

    def stop_self(self) -> None:
        self.client("ec2").stop_instances(InstanceIds=[self.instance_id])


class NoCloud(Cloud):
    """No AWS: parameters come from a dict (tests / local runs)."""

    def __init__(self, params: dict[str, str] | None = None):
        super().__init__("/smartsched", "none", instance_id="i-local", region="local")
        self.params = dict(params or {})
        self.events: list[tuple[str, object]] = []

    def get_param(self, name: str, decrypt: bool = True) -> str | None:
        return self.params.get(name)

    def put_param(self, name: str, value: str, secure: bool) -> None:
        self.params[name] = value
        self.events.append(("put", name))

    def heartbeat(self, ci_running: bool) -> None:
        self.events.append(("heartbeat", ci_running))

    def set_alarm_actions(self, enabled: bool) -> None:
        self.events.append(("alarm_actions", enabled))

    def stop_self(self) -> None:
        self.events.append(("stop", self.instance_id))
