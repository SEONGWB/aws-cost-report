"""비용 데이터 수집 클라이언트.

CostExplorerClient(추상) ─┬─ AwsCostExplorerClient   : 실제 AWS Cost Explorer
                          └─ MockCostExplorerClient  : 결정적(seed) 가짜 데이터
"""
from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.models import DailyCost

log = logging.getLogger(__name__)


class CostExplorerClient(ABC):
    @abstractmethod
    def fetch_daily(self, start: date, end: date) -> list[DailyCost]:
        """[start, end) 구간의 일별 · 서비스별 비용. end는 포함하지 않는다."""


class AwsCostExplorerClient(CostExplorerClient):
    """AWS Cost Explorer (ce:GetCostAndUsage).

    자격증명은 코드에 두지 않는다 → boto3 기본 체인이 찾는다.
      로컬: ~/.aws 또는 환경변수 / AWS 위: IAM 역할
    """

    def __init__(self, settings: Settings, ce_client: Any | None = None) -> None:
        if ce_client is None:
            import boto3  # mock 모드에서는 boto3 import 자체를 하지 않음

            ce_client = boto3.client("ce", region_name=settings.ce_region)
        self._ce = ce_client
        self._metric = settings.cost_metric

    def fetch_daily(self, start: date, end: date) -> list[DailyCost]:
        request: dict[str, Any] = {
            "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
            "Granularity": "DAILY",
            "Metrics": [self._metric],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        }
        result: list[DailyCost] = []
        while True:
            log.info("Cost Explorer 호출: %s ~ %s", start, end)
            response = self._ce.get_cost_and_usage(**request)
            for day in response["ResultsByTime"]:
                usage_date = date.fromisoformat(day["TimePeriod"]["Start"])
                for group in day.get("Groups", []):
                    metric = group["Metrics"][self._metric]
                    result.append(
                        DailyCost(
                            usage_date=usage_date,
                            service=group["Keys"][0],
                            amount=Decimal(metric["Amount"]),
                            currency=metric.get("Unit", "USD"),
                        )
                    )
            token = response.get("NextPageToken")
            if not token:
                return result
            request["NextPageToken"] = token


class MockCostExplorerClient(CostExplorerClient):
    """날짜를 seed로 쓰는 가짜 데이터 — 같은 날짜는 항상 같은 값 (테스트 재현성)."""

    SERVICES: dict[str, float] = {
        "Amazon Elastic Compute Cloud - Compute": 18.0,
        "Amazon Relational Database Service": 9.5,
        "Amazon Elastic Kubernetes Service": 2.4,
        "Amazon Simple Storage Service": 2.1,
        "Amazon Virtual Private Cloud": 1.3,
        "AmazonCloudWatch": 0.8,
        "AWS Lambda": 0.25,
        "Amazon Route 53": 0.05,
    }

    def fetch_daily(self, start: date, end: date) -> list[DailyCost]:
        result: list[DailyCost] = []
        day = start
        while day < end:
            rnd = random.Random(day.toordinal())
            for service, base in self.SERVICES.items():
                amount = Decimal(str(round(base * rnd.uniform(0.7, 1.3), 6)))
                result.append(DailyCost(day, service, amount, "USD"))
            day += timedelta(days=1)
        return result


def build_cost_explorer_client(settings: Settings) -> CostExplorerClient:
    if settings.cost_source == "aws":
        return AwsCostExplorerClient(settings)
    if settings.cost_source == "mock":
        return MockCostExplorerClient()
    raise ValueError(f"알 수 없는 COST_SOURCE: {settings.cost_source!r} (mock | aws)")
