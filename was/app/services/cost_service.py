"""비용 비즈니스 로직 — 수집(collect)과 조회(report)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.clients.cost_explorer import CostExplorerClient
from app.repositories.cost_repository import CostRepository
from app.schemas import CollectResult, DailyReport, ServiceCost, TrendPoint, TrendReport

log = logging.getLogger(__name__)


def yesterday_utc() -> date:
    # Cost Explorer는 UTC 기준이고 당일 데이터는 집계 중 → 기본 기준일은 '어제'
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def _money(value: Decimal | float) -> float:
    """금액은 센트 단위(소수 2자리)로 반올림. 증감은 반올림된 값끼리 계산해 화면 숫자와 일치시킨다."""
    return round(float(value), 2)


class CostService:
    def __init__(self, client: CostExplorerClient, repository: CostRepository) -> None:
        self._client = client
        self._repo = repository

    # ------------------------------------------------------------------ 수집
    def collect(self, start: date, end: date) -> CollectResult:
        """[start, end) 구간을 Cost Explorer에서 가져와 저장소에 반영."""
        if start >= end:
            raise ValueError("start는 end보다 앞이어야 합니다")
        costs = self._client.fetch_daily(start, end)
        rows = self._repo.replace_range(start, end, costs)
        log.info("수집 완료: %s ~ %s (%d rows)", start, end, rows)
        return CollectResult(start=start, end=end, rows=rows)

    def collect_recent(self, days: int) -> CollectResult:
        end = yesterday_utc() + timedelta(days=1)  # 어제까지 포함
        return self.collect(end - timedelta(days=days), end)

    # ------------------------------------------------------------------ 조회
    def daily_report(self, target: date) -> DailyReport:
        prev = target - timedelta(days=1)
        today_rows = {c.service: c for c in self._repo.find_by_date(target)}
        prev_rows = {c.service: c for c in self._repo.find_by_date(prev)}

        services: list[ServiceCost] = []
        for name in today_rows.keys() | prev_rows.keys():
            cur = today_rows[name].amount if name in today_rows else Decimal(0)
            before = prev_rows[name].amount if name in prev_rows else Decimal(0)
            if cur == 0 and before == 0:
                continue
            amount, prev_amount = _money(cur), _money(before)
            services.append(ServiceCost(
                service=name,
                amount=amount,
                prev_amount=prev_amount,
                change=_money(amount - prev_amount),
            ))
        services.sort(key=lambda s: s.amount, reverse=True)

        total = sum((c.amount for c in today_rows.values()), Decimal(0))
        prev_total = sum((c.amount for c in prev_rows.values()), Decimal(0))
        mtd = sum(self._repo.daily_totals(target.replace(day=1), target).values(), Decimal(0))
        currency = next(iter(today_rows.values())).currency if today_rows else "USD"

        total_r, prev_r = _money(total), _money(prev_total)
        return DailyReport(
            date=target,
            currency=currency,
            has_data=bool(today_rows),
            total=total_r,
            prev_total=prev_r,
            change=_money(total_r - prev_r),
            change_pct=round((total_r - prev_r) / prev_r * 100, 1) if prev_r else None,
            month_to_date=_money(mtd),
            services=services,
        )

    def trend(self, end: date, days: int) -> TrendReport:
        start = end - timedelta(days=days - 1)
        totals = self._repo.daily_totals(start, end)
        points = [
            TrendPoint(date=d, total=_money(totals.get(d, Decimal(0))))
            for d in (start + timedelta(days=i) for i in range(days))
        ]
        return TrendReport(currency="USD", points=points)

    def latest_date(self) -> date | None:
        return self._repo.latest_date()
