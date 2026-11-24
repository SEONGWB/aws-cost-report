"""비용 조회 API.

sync(def) 핸들러로 둔다: psycopg/boto3가 동기 라이브러리라
FastAPI가 스레드풀에서 실행 → 이벤트 루프를 막지 않는다.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app import __version__
from app.config import Settings
from app.schemas import DailyReport, Meta, TrendReport
from app.services.cost_service import CostService, yesterday_utc


class CostController:
    def __init__(self, service: CostService, settings: Settings) -> None:
        self._service = service
        self._settings = settings
        self.router = APIRouter(prefix="/api", tags=["costs"])
        self.router.add_api_route("/meta", self.meta, methods=["GET"], response_model=Meta)
        self.router.add_api_route("/costs/daily", self.daily, methods=["GET"], response_model=DailyReport)
        self.router.add_api_route("/costs/trend", self.trend, methods=["GET"], response_model=TrendReport)

    def meta(self) -> Meta:
        return Meta(
            version=__version__,
            cost_source=self._settings.cost_source,
            repository=self._settings.repository,
            latest_date=self._service.latest_date(),
        )

    def daily(
        self,
        target: date | None = Query(None, alias="date", description="YYYY-MM-DD (기본: 어제 UTC)"),
    ) -> DailyReport:
        return self._service.daily_report(target or yesterday_utc())

    def trend(
        self,
        days: int = Query(14, ge=1, le=90),
        end: date | None = Query(None, description="YYYY-MM-DD, 포함 (기본: 어제 UTC)"),
    ) -> TrendReport:
        return self._service.trend(end or yesterday_utc(), days)
