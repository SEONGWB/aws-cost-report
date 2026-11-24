"""AwsCostExplorerClient 파싱 테스트 — botocore Stubber로 AWS 호출 없이 검증."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import boto3
from botocore.stub import Stubber

from app.clients.cost_explorer import AwsCostExplorerClient
from app.config import Settings


def _day(start: str, end: str, groups: list[tuple[str, str]]) -> dict:
    return {
        "TimePeriod": {"Start": start, "End": end},
        "Total": {},
        "Groups": [
            {"Keys": [svc], "Metrics": {"UnblendedCost": {"Amount": amt, "Unit": "USD"}}}
            for svc, amt in groups
        ],
        "Estimated": False,
    }


def test_parses_groups_and_follows_pagination():
    ce = boto3.client("ce", region_name="us-east-1",
                      aws_access_key_id="test", aws_secret_access_key="test")
    base_request = {
        "TimePeriod": {"Start": "2026-11-14", "End": "2026-11-16"},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
    }
    with Stubber(ce) as stub:
        stub.add_response(
            "get_cost_and_usage",
            {"ResultsByTime": [_day("2026-11-14", "2026-11-15", [("EC2", "1.5"), ("S3", "0.25")])],
             "NextPageToken": "page2"},
            base_request,
        )
        stub.add_response(
            "get_cost_and_usage",
            {"ResultsByTime": [_day("2026-11-15", "2026-11-16", [("EC2", "2.0")])]},
            {**base_request, "NextPageToken": "page2"},
        )
        client = AwsCostExplorerClient(Settings(cost_source="aws"), ce_client=ce)
        rows = client.fetch_daily(date(2026, 11, 14), date(2026, 11, 16))
        stub.assert_no_pending_responses()

    assert [(r.usage_date, r.service, r.amount) for r in rows] == [
        (date(2026, 11, 14), "EC2", Decimal("1.5")),
        (date(2026, 11, 14), "S3", Decimal("0.25")),
        (date(2026, 11, 15), "EC2", Decimal("2.0")),
    ]
    assert all(r.currency == "USD" for r in rows)
