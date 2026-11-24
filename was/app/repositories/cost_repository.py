"""비용 데이터 저장소.

CostRepository(추상) ─┬─ PostgresCostRepository : PostgreSQL (로컬 컨테이너 또는 RDS)
                      └─ InMemoryCostRepository : DB 없이 개발/테스트용
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.config import Settings
from app.models import Budget, DailyCost

log = logging.getLogger(__name__)


class CostRepository(ABC):
    def open(self) -> None:
        """리소스 준비 (커넥션 풀, 스키마)."""

    def close(self) -> None:
        """리소스 정리."""

    @abstractmethod
    def ping(self) -> bool: ...

    @abstractmethod
    def replace_range(self, start: date, end: date, costs: list[DailyCost]) -> int:
        """[start, end) 구간 데이터를 통째로 교체한다 (재수집 시 값 보정 반영)."""

    @abstractmethod
    def find_by_date(self, usage_date: date) -> list[DailyCost]: ...

    @abstractmethod
    def daily_totals(self, start: date, end: date) -> dict[date, Decimal]:
        """[start, end] 구간(양끝 포함) 일별 합계."""

    @abstractmethod
    def latest_date(self) -> date | None: ...

    @abstractmethod
    def service_totals(self, start: date, end: date) -> dict[str, Decimal]:
        """[start, end) 구간 서비스별 합계."""

    # ---- 월 예산 (등록 · 조회 · 수정)
    @abstractmethod
    def create_budget(self, month: date, service: str, amount: Decimal) -> Budget:
        """같은 (월, 서비스)가 이미 있으면 BudgetExistsError."""

    @abstractmethod
    def get_budget(self, budget_id: int) -> Budget | None: ...

    @abstractmethod
    def list_budgets(self, month: date) -> list[Budget]: ...

    @abstractmethod
    def update_budget(self, budget_id: int, amount: Decimal) -> Budget | None: ...


class BudgetExistsError(Exception):
    """같은 월 · 서비스의 예산이 이미 있음."""


# ---------------------------------------------------------------------------
class InMemoryCostRepository(CostRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[date, str], DailyCost] = {}
        self._budgets: dict[int, Budget] = {}

    def ping(self) -> bool:
        return True

    def replace_range(self, start: date, end: date, costs: list[DailyCost]) -> int:
        for key in [k for k in self._rows if start <= k[0] < end]:
            del self._rows[key]
        for cost in costs:
            self._rows[(cost.usage_date, cost.service)] = cost
        return len(costs)

    def find_by_date(self, usage_date: date) -> list[DailyCost]:
        return [c for (d, _), c in self._rows.items() if d == usage_date]

    def daily_totals(self, start: date, end: date) -> dict[date, Decimal]:
        totals: dict[date, Decimal] = defaultdict(Decimal)
        for (d, _), cost in self._rows.items():
            if start <= d <= end:
                totals[d] += cost.amount
        return dict(totals)

    def latest_date(self) -> date | None:
        return max((d for d, _ in self._rows), default=None)

    def service_totals(self, start: date, end: date) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for (d, svc), cost in self._rows.items():
            if start <= d < end:
                totals[svc] += cost.amount
        return dict(totals)

    def create_budget(self, month: date, service: str, amount: Decimal) -> Budget:
        if any(b.month == month and b.service == service for b in self._budgets.values()):
            raise BudgetExistsError(service)
        budget = Budget(len(self._budgets) + 1, month, service, amount)
        self._budgets[budget.id] = budget
        return budget

    def get_budget(self, budget_id: int) -> Budget | None:
        return self._budgets.get(budget_id)

    def list_budgets(self, month: date) -> list[Budget]:
        return sorted((b for b in self._budgets.values() if b.month == month), key=lambda b: b.service)

    def update_budget(self, budget_id: int, amount: Decimal) -> Budget | None:
        old = self._budgets.get(budget_id)
        if old is None:
            return None
        self._budgets[budget_id] = Budget(old.id, old.month, old.service, amount)
        return self._budgets[budget_id]


# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cost_daily (
    usage_date   date           NOT NULL,
    service      text           NOT NULL,
    amount       numeric(20,10) NOT NULL,
    currency     varchar(8)     NOT NULL DEFAULT 'USD',
    collected_at timestamptz    NOT NULL DEFAULT now(),
    PRIMARY KEY (usage_date, service)
);
CREATE TABLE IF NOT EXISTS budget (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    month      date          NOT NULL,
    service    text          NOT NULL,
    amount     numeric(12,2) NOT NULL CHECK (amount > 0),
    created_at timestamptz   NOT NULL DEFAULT now(),
    updated_at timestamptz   NOT NULL DEFAULT now(),
    UNIQUE (month, service)
)
"""


class PostgresCostRepository(CostRepository):
    def __init__(self, settings: Settings, connect_retries: int = 30) -> None:
        if not settings.db_password:
            raise ValueError("DB_PASSWORD 환경변수가 필요합니다 (기본값 없음)")
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            settings.db_conninfo,
            min_size=1,
            max_size=settings.db_pool_max,
            open=False,
            kwargs={"connect_timeout": 5},
        )
        self._settings = settings
        self._retries = connect_retries

    def open(self) -> None:
        # DB가 WAS보다 늦게 뜰 수 있으므로 재시도
        self._pool.open(wait=False)
        for attempt in range(1, self._retries + 1):
            try:
                with self._pool.connection(timeout=5) as conn:
                    conn.execute(SCHEMA_SQL)
                log.info("DB 연결 성공: %s:%s/%s", self._settings.db_host,
                         self._settings.db_port, self._settings.db_name)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("DB 연결 대기 (%d/%d): %s", attempt, self._retries, exc)
                time.sleep(2)
        raise RuntimeError("DB에 연결할 수 없습니다")

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> bool:
        try:
            with self._pool.connection(timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    def replace_range(self, start: date, end: date, costs: list[DailyCost]) -> int:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM cost_daily WHERE usage_date >= %s AND usage_date < %s",
                    (start, end),
                )
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO cost_daily (usage_date, service, amount, currency) "
                        "VALUES (%s, %s, %s, %s)",
                        [(c.usage_date, c.service, c.amount, c.currency) for c in costs],
                    )
        return len(costs)

    def find_by_date(self, usage_date: date) -> list[DailyCost]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT usage_date, service, amount, currency FROM cost_daily "
                "WHERE usage_date = %s",
                (usage_date,),
            ).fetchall()
        return [DailyCost(*row) for row in rows]

    def daily_totals(self, start: date, end: date) -> dict[date, Decimal]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT usage_date, sum(amount) FROM cost_daily "
                "WHERE usage_date BETWEEN %s AND %s GROUP BY usage_date",
                (start, end),
            ).fetchall()
        return {d: total for d, total in rows}

    def latest_date(self) -> date | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT max(usage_date) FROM cost_daily").fetchone()
        return row[0] if row else None

    def service_totals(self, start: date, end: date) -> dict[str, Decimal]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT service, sum(amount) FROM cost_daily "
                "WHERE usage_date >= %s AND usage_date < %s GROUP BY service",
                (start, end),
            ).fetchall()
        return {svc: total for svc, total in rows}

    _BUDGET_COLS = "id, month, service, amount"

    def create_budget(self, month: date, service: str, amount: Decimal) -> Budget:
        from psycopg.errors import UniqueViolation

        try:
            with self._pool.connection() as conn:
                row = conn.execute(
                    f"INSERT INTO budget (month, service, amount) VALUES (%s, %s, %s) "
                    f"RETURNING {self._BUDGET_COLS}",
                    (month, service, amount),
                ).fetchone()
        except UniqueViolation as exc:
            raise BudgetExistsError(service) from exc
        return Budget(*row)

    def get_budget(self, budget_id: int) -> Budget | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {self._BUDGET_COLS} FROM budget WHERE id = %s", (budget_id,)
            ).fetchone()
        return Budget(*row) if row else None

    def list_budgets(self, month: date) -> list[Budget]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {self._BUDGET_COLS} FROM budget WHERE month = %s ORDER BY service",
                (month,),
            ).fetchall()
        return [Budget(*r) for r in rows]

    def update_budget(self, budget_id: int, amount: Decimal) -> Budget | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"UPDATE budget SET amount = %s, updated_at = now() WHERE id = %s "
                f"RETURNING {self._BUDGET_COLS}",
                (amount, budget_id),
            ).fetchone()
        return Budget(*row) if row else None


def build_cost_repository(settings: Settings) -> CostRepository:
    if settings.repository == "postgres":
        return PostgresCostRepository(settings)
    if settings.repository == "memory":
        return InMemoryCostRepository()
    raise ValueError(f"알 수 없는 REPOSITORY: {settings.repository!r} (postgres | memory)")
