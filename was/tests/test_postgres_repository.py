"""PostgresCostRepository 통합 테스트 — TEST_DB_HOST 가 있을 때만 실행.

    ⚠️ 테이블을 TRUNCATE 하므로 운영 DB(costdb)에 절대 실행하지 않는다. 테스트 전용 DB를 따로 띄운다.
    TEST_DB_HOST=localhost TEST_DB_PORT=55432 TEST_DB_PASSWORD=... pytest -m postgres
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from app.config import Settings
from app.models import DailyCost
from app.repositories.cost_repository import BudgetExistsError, PostgresCostRepository

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not os.getenv("TEST_DB_HOST"), reason="TEST_DB_HOST 미설정"),
]


@pytest.fixture
def repo():
    settings = Settings(
        repository="postgres",
        db_host=os.environ["TEST_DB_HOST"],
        db_port=int(os.getenv("TEST_DB_PORT", "5432")),
        db_password=os.environ["TEST_DB_PASSWORD"],
    )
    r = PostgresCostRepository(settings, connect_retries=5)
    r.open()
    with r._pool.connection() as conn:  # noqa: SLF001 - 테스트 격리
        conn.execute("TRUNCATE cost_daily, budget")
    yield r
    r.close()


def test_roundtrip(repo):
    d = date(2026, 11, 15)
    repo.replace_range(d, date(2026, 11, 16), [
        DailyCost(d, "EC2", Decimal("1.2345678901")),
        DailyCost(d, "S3", Decimal("0.5")),
    ])
    rows = {c.service: c.amount for c in repo.find_by_date(d)}
    assert rows == {"EC2": Decimal("1.2345678901"), "S3": Decimal("0.5")}
    assert repo.daily_totals(d, d) == {d: Decimal("1.7345678901")}
    assert repo.latest_date() == d
    assert repo.ping()


def test_replace_range_removes_stale_rows(repo):
    d = date(2026, 11, 15)
    repo.replace_range(d, date(2026, 11, 16), [DailyCost(d, "OLD", Decimal("1"))])
    repo.replace_range(d, date(2026, 11, 16), [DailyCost(d, "NEW", Decimal("2"))])
    assert [c.service for c in repo.find_by_date(d)] == ["NEW"]


def test_budget_create_update_and_unique(repo):
    m = date(2026, 11, 1)
    b = repo.create_budget(m, "EC2", Decimal("300"))
    assert repo.get_budget(b.id).amount == Decimal("300.00")
    assert repo.update_budget(b.id, Decimal("450.5")).amount == Decimal("450.50")
    assert [x.service for x in repo.list_budgets(m)] == ["EC2"]
    with pytest.raises(BudgetExistsError):
        repo.create_budget(m, "EC2", Decimal("1"))
    assert repo.update_budget(999999, Decimal("1")) is None


def test_service_totals_month_range(repo):
    repo.replace_range(date(2026, 10, 31), date(2026, 11, 3), [
        DailyCost(date(2026, 10, 31), "EC2", Decimal("9")),
        DailyCost(date(2026, 11, 1), "EC2", Decimal("1")),
        DailyCost(date(2026, 11, 2), "EC2", Decimal("2")),
    ])
    assert repo.service_totals(date(2026, 11, 1), date(2026, 12, 1)) == {"EC2": Decimal("3")}
