"""WAS 애플리케이션 조립.

Application 은 FastAPI 를 상속하지 않고 '가지고 있다' (composition).
의존성(설정 · 클라이언트 · 저장소)은 생성자로 주입 → 테스트에서 가짜로 교체 가능.

    Application
     ├─ HealthController ── CostRepository
     ├─ CostController ──── CostService ─┬─ CostExplorerClient
     │                                   └─ CostRepository
     └─ BudgetController ── BudgetService ── CostRepository
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.clients.cost_explorer import CostExplorerClient, build_cost_explorer_client
from app.config import Settings
from app.controllers.budget_controller import BudgetController
from app.controllers.cost_controller import CostController
from app.controllers.health_controller import HealthController
from app.repositories.cost_repository import CostRepository, build_cost_repository
from app.services.budget_service import BudgetService
from app.services.cost_service import CostService


class Application:
    def __init__(
        self,
        settings: Settings | None = None,
        client: CostExplorerClient | None = None,
        repository: CostRepository | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        logging.basicConfig(  # 로그는 stdout (컨테이너 표준)
            level=self.settings.log_level,
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        )
        self.repository = repository or build_cost_repository(self.settings)
        self.client = client or build_cost_explorer_client(self.settings)
        self.service = CostService(self.client, self.repository)
        self.budget_service = BudgetService(self.repository)

        self.api = FastAPI(
            title="AWS Cost Report API",
            version=__version__,
            lifespan=self._lifespan,
        )
        self.api.include_router(HealthController(self.repository).router)
        self.api.include_router(CostController(self.service, self.settings).router)
        self.api.include_router(BudgetController(self.budget_service).router)
        # DB 연결 실패는 평문 500 대신 JSON 503 (일시적 장애임을 알림)
        self.api.add_exception_handler(psycopg.OperationalError, self._db_unavailable)

    @staticmethod
    async def _db_unavailable(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).error("DB 사용 불가: %s", exc)
        return JSONResponse(
            {"detail": "database unavailable"}, status_code=503, headers={"Retry-After": "10"}
        )

    @asynccontextmanager
    async def _lifespan(self, _: FastAPI) -> AsyncIterator[None]:
        self.repository.open()
        try:
            yield
        finally:
            self.repository.close()
