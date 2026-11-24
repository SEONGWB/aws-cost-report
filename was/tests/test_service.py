from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.clients.cost_explorer import CostExplorerClient
from app.models import DailyCost
from app.repositories.cost_repository import InMemoryCostRepository
from app.services.cost_service import CostService, yesterday_utc


class FixedClient(CostExplorerClient):
    def __init__(self, rows: list[DailyCost]) -> None:
        self.rows = rows
        self.calls: list[tuple[date, date]] = []

    def fetch_daily(self, start, end):
        self.calls.append((start, end))
        return [r for r in self.rows if start <= r.usage_date < end]


D1, D2 = date(2026, 11, 14), date(2026, 11, 15)


def make_service(rows):
    client = FixedClient(rows)
    return CostService(client, InMemoryCostRepository()), client


def test_change_and_pct():
    service, _ = make_service([
        DailyCost(D1, "EC2", Decimal("10")),
        DailyCost(D1, "S3", Decimal("2")),
        DailyCost(D2, "EC2", Decimal("12")),
        DailyCost(D2, "S3", Decimal("3")),
    ])
    service.collect(D1, D2 + timedelta(days=1))
    report = service.daily_report(D2)
    assert report.total == 15 and report.prev_total == 12
    assert report.change == 3 and report.change_pct == 25.0
    assert [s.service for s in report.services] == ["EC2", "S3"]


def test_service_appears_or_disappears():
    service, _ = make_service([
        DailyCost(D1, "OLD", Decimal("5")),
        DailyCost(D2, "NEW", Decimal("7")),
    ])
    service.collect(D1, D2 + timedelta(days=1))
    by_name = {s.service: s for s in service.daily_report(D2).services}
    assert by_name["OLD"].amount == 0 and by_name["OLD"].change == -5
    assert by_name["NEW"].prev_amount == 0 and by_name["NEW"].change == 7


def test_zero_rows_are_hidden():
    service, _ = make_service([
        DailyCost(D1, "Tax", Decimal("0")),
        DailyCost(D2, "Tax", Decimal("0")),
        DailyCost(D2, "EC2", Decimal("1")),
    ])
    service.collect(D1, D2 + timedelta(days=1))
    assert [s.service for s in service.daily_report(D2).services] == ["EC2"]


def test_recollect_replaces_range():
    """재수집 시 이전 값이 남지 않고 교체되어야 한다 (Cost Explorer 값 보정 대응)."""
    service, client = make_service([DailyCost(D2, "EC2", Decimal("1"))])
    service.collect(D2, D2 + timedelta(days=1))
    client.rows = [DailyCost(D2, "EC2", Decimal("9"))]
    service.collect(D2, D2 + timedelta(days=1))
    assert service.daily_report(D2).total == 9


def test_month_to_date():
    rows = [DailyCost(date(2026, 11, d), "EC2", Decimal("1")) for d in range(1, 16)]
    rows.append(DailyCost(date(2026, 10, 31), "EC2", Decimal("100")))  # 전월 제외
    service, _ = make_service(rows)
    service.collect(date(2026, 10, 31), date(2026, 11, 16))
    assert service.daily_report(D2).month_to_date == 15


def test_trend_fills_missing_days_with_zero():
    service, _ = make_service([DailyCost(D2, "EC2", Decimal("4"))])
    service.collect(D2, D2 + timedelta(days=1))
    points = service.trend(D2, 3).points
    assert [p.total for p in points] == [0, 0, 4]


def test_collect_recent_range():
    service, client = make_service([])
    service.collect_recent(3)
    start, end = client.calls[0]
    assert end == yesterday_utc() + timedelta(days=1)
    assert (end - start).days == 3


def test_collect_invalid_range():
    service, _ = make_service([])
    with pytest.raises(ValueError):
        service.collect(D2, D2)
