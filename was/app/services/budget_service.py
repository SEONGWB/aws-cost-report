"""월 예산 비즈니스 로직 — 등록 · 조회 · 수정, 실제 사용액과 비교."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import Budget
from app.repositories.cost_repository import CostRepository
from app.schemas import BudgetView


def parse_month(value: str) -> date:
    """'2026-11' → date(2026, 11, 1)"""
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _next_month(month: date) -> date:
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)


class BudgetNotFoundError(Exception):
    pass


class BudgetService:
    def __init__(self, repository: CostRepository) -> None:
        self._repo = repository

    def _view(self, budget: Budget, spent_by_service: dict[str, Decimal]) -> BudgetView:
        amount = round(float(budget.amount), 2)
        spent = round(float(spent_by_service.get(budget.service, Decimal(0))), 2)
        return BudgetView(
            id=budget.id,
            month=budget.month.strftime("%Y-%m"),
            service=budget.service,
            amount=amount,
            spent=spent,
            usage_pct=round(spent / amount * 100, 1),
        )

    def _spent(self, month: date) -> dict[str, Decimal]:
        return self._repo.service_totals(month, _next_month(month))

    def create(self, month: str, service: str, amount: float) -> BudgetView:
        m = parse_month(month)
        budget = self._repo.create_budget(m, service.strip(), Decimal(str(amount)))
        return self._view(budget, self._spent(m))

    def get(self, budget_id: int) -> BudgetView:
        budget = self._repo.get_budget(budget_id)
        if budget is None:
            raise BudgetNotFoundError(budget_id)
        return self._view(budget, self._spent(budget.month))

    def list(self, month: str) -> list[BudgetView]:
        m = parse_month(month)
        spent = self._spent(m)
        return [self._view(b, spent) for b in self._repo.list_budgets(m)]

    def update(self, budget_id: int, amount: float) -> BudgetView:
        budget = self._repo.update_budget(budget_id, Decimal(str(amount)))
        if budget is None:
            raise BudgetNotFoundError(budget_id)
        return self._view(budget, self._spent(budget.month))
