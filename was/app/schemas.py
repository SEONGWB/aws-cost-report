"""API 응답 스키마 (pydantic) — /docs 에 자동 문서화된다."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ServiceCost(BaseModel):
    service: str
    amount: float
    prev_amount: float
    change: float


class DailyReport(BaseModel):
    date: date
    currency: str
    has_data: bool
    total: float
    prev_total: float
    change: float
    change_pct: float | None
    month_to_date: float
    services: list[ServiceCost]


class TrendPoint(BaseModel):
    date: date
    total: float


class TrendReport(BaseModel):
    currency: str
    points: list[TrendPoint]


class Meta(BaseModel):
    version: str
    cost_source: str
    repository: str
    latest_date: date | None


class CollectResult(BaseModel):
    start: date
    end: date
    rows: int


# ---- 월 예산 (등록 · 조회 · 수정)
class BudgetCreate(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-11"])
    service: str = Field(min_length=1, max_length=100, examples=["Amazon Elastic Compute Cloud - Compute"])
    amount: float = Field(gt=0, le=1_000_000, examples=[300])


class BudgetUpdate(BaseModel):
    amount: float = Field(gt=0, le=1_000_000, examples=[350])


class BudgetView(BaseModel):
    id: int
    month: str
    service: str
    amount: float
    spent: float              # 해당 월 누적 사용액
    usage_pct: float          # spent / amount * 100
