"""월 예산 API — 등록(POST) · 조회(GET) · 수정(PUT)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.repositories.cost_repository import BudgetExistsError
from app.schemas import BudgetCreate, BudgetUpdate, BudgetView
from app.services.budget_service import BudgetNotFoundError, BudgetService
from app.services.cost_service import yesterday_utc


class BudgetController:
    def __init__(self, service: BudgetService) -> None:
        self._service = service
        self.router = APIRouter(prefix="/api/budgets", tags=["budgets"])
        self.router.add_api_route("", self.list, methods=["GET"], response_model=list[BudgetView])
        self.router.add_api_route("", self.create, methods=["POST"], response_model=BudgetView,
                                  status_code=status.HTTP_201_CREATED)
        self.router.add_api_route("/{budget_id}", self.get, methods=["GET"], response_model=BudgetView)
        self.router.add_api_route("/{budget_id}", self.update, methods=["PUT"], response_model=BudgetView)

    def list(
        self,
        month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM (기본: 어제가 속한 달)"),
    ) -> list[BudgetView]:
        return self._service.list(month or yesterday_utc().strftime("%Y-%m"))

    def create(self, body: BudgetCreate) -> BudgetView:
        try:
            return self._service.create(body.month, body.service, body.amount)
        except BudgetExistsError:
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록된 예산입니다 (같은 월 · 서비스)")

    def get(self, budget_id: int) -> BudgetView:
        try:
            return self._service.get(budget_id)
        except BudgetNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "예산을 찾을 수 없습니다")

    def update(self, budget_id: int, body: BudgetUpdate) -> BudgetView:
        try:
            return self._service.update(budget_id, body.amount)
        except BudgetNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "예산을 찾을 수 없습니다")
