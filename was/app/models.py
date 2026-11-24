"""도메인 모델."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DailyCost:
    """특정 일자 · 특정 서비스의 비용 1건."""

    usage_date: date
    service: str
    amount: Decimal
    currency: str = "USD"


@dataclass(frozen=True)
class Budget:
    """서비스별 월 예산 1건 (사용자가 등록 · 수정)."""

    id: int
    month: date          # 해당 월 1일
    service: str
    amount: Decimal
