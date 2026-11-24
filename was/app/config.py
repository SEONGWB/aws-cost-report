"""환경변수 기반 설정.

모든 설정은 환경변수로만 받는다 (12-factor).
  - 실행 환경에서 DB_HOST, DB_PASSWORD 등을 지정한다
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    # 비용 데이터 출처: mock(가짜, 과금 없음) | aws(Cost Explorer 실제 호출, 요청당 $0.01)
    cost_source: str = "mock"
    # Cost Explorer 엔드포인트는 us-east-1 고정
    ce_region: str = "us-east-1"
    # UnblendedCost | AmortizedCost | NetUnblendedCost ...
    cost_metric: str = "UnblendedCost"

    # 저장소: postgres | memory(DB 없이 개발/테스트용)
    repository: str = "postgres"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "costdb"
    db_user: str = "cost"
    # 기본값 없음: 비밀번호는 반드시 DB_PASSWORD 환경변수로 주입한다
    db_password: str = ""
    # RDS 등 SSL 을 강제하는 DB 는 require
    db_sslmode: str = "prefer"
    db_pool_max: int = 5

    # 수집 기본 범위: 오늘 기준 N일 전 ~ 어제 (Cost Explorer는 최근 며칠 값을 보정하므로 재수집)
    collect_days: int = 3

    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            cost_source=_env("COST_SOURCE", cls.cost_source).lower(),
            ce_region=_env("CE_REGION", cls.ce_region),
            cost_metric=_env("COST_METRIC", cls.cost_metric),
            repository=_env("REPOSITORY", cls.repository).lower(),
            db_host=_env("DB_HOST", cls.db_host),
            db_port=int(_env("DB_PORT", str(cls.db_port))),
            db_name=_env("DB_NAME", cls.db_name),
            db_user=_env("DB_USER", cls.db_user),
            db_password=_env("DB_PASSWORD", cls.db_password),
            db_sslmode=_env("DB_SSLMODE", cls.db_sslmode),
            db_pool_max=int(_env("DB_POOL_MAX", str(cls.db_pool_max))),
            collect_days=int(_env("COLLECT_DAYS", str(cls.collect_days))),
            log_level=_env("LOG_LEVEL", cls.log_level).upper(),
        )

    @property
    def db_conninfo(self) -> str:
        # 비밀번호가 로그에 찍히지 않도록 이 값은 절대 로깅하지 않는다
        from psycopg.conninfo import make_conninfo  # 특수문자 비밀번호도 안전하게 이스케이프

        return make_conninfo(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password,
            sslmode=self.db_sslmode,
            application_name="aws-cost-report",
        )
