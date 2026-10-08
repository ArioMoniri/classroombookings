"""Helpers for infra/aws tests (stubbed AWS clients): botocore Stubber only, no network, fake credentials."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import boto3
from botocore.stub import Stubber

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import smartsched_aws as sa

# botocore operation -> IAM action, where the two differ (Budgets uses coarse IAM actions).
IAM_ACTION_OVERRIDES = {
    ("budgets", "CreateBudget"): "budgets:ModifyBudget",
    ("budgets", "UpdateBudget"): "budgets:ModifyBudget",
    ("budgets", "DeleteBudget"): "budgets:ModifyBudget",
    ("budgets", "CreateNotification"): "budgets:ModifyBudget",
    ("budgets", "CreateSubscriber"): "budgets:ModifyBudget",
    ("budgets", "DescribeBudget"): "budgets:ViewBudget",
    ("budgets", "DescribeNotificationsForBudget"): "budgets:ViewBudget",
    ("budgets", "DescribeSubscribersForNotification"): "budgets:ViewBudget",
    ("resourcegroupstaggingapi", "GetResources"): "tag:GetResources",
}
PREFIX = {"resourcegroupstaggingapi": "tag", "ce": "ce"}


class StubAws(sa.Aws):
    """sa.Aws whose clients are real botocore clients with an active Stubber (one per service+region)."""

    def __init__(self, region: str = "us-east-1"):
        super().__init__(region)
        self.session = boto3.session.Session(aws_access_key_id="AKIATESTTESTTESTTEST",
                                             aws_secret_access_key="test-secret", region_name=region)
        self.stubbers: dict[tuple[str, str], Stubber] = {}
        self.calls: list[tuple[str, str]] = []

    def client(self, service: str, region: str | None = None) -> Any:
        reg = sa.GLOBAL_REGION if service in self.GLOBAL_SERVICES else (region or self.region)
        key = (service, reg)
        if key not in self._clients:
            c = self.session.client(service, region_name=reg)
            st = Stubber(c)
            st.activate()
            c.meta.events.register("before-call", self._record)
            self._clients[key] = c
            self.stubbers[key] = st
        return self._clients[key]

    def _record(self, model: Any, **_: Any) -> None:
        self.calls.append((model.service_model.service_name, model.name))

    def stub(self, service: str, region: str | None = None) -> Stubber:
        self.client(service, region)
        reg = sa.GLOBAL_REGION if service in self.GLOBAL_SERVICES else (region or self.region)
        return self.stubbers[(service, reg)]

    def assert_done(self) -> None:
        for st in self.stubbers.values():
            st.assert_no_pending_responses()

    def iam_actions(self) -> set[str]:
        out = set()
        for svc, op in self.calls:
            if svc == "sts" and op == "GetCallerIdentity":
                continue  # needs no permission
            out.add(IAM_ACTION_OVERRIDES.get((svc, op), f"{PREFIX.get(svc, svc)}:{op}"))
        return out


def price_item(usd: str) -> str:
    return json.dumps({"product": {}, "terms": {"OnDemand": {"X.Y": {"priceDimensions": {
        "X.Y.Z": {"unit": "Hrs", "pricePerUnit": {"USD": usd}}}}}}})
