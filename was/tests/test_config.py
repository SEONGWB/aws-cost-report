from __future__ import annotations

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.config import Settings


def test_defaults(monkeypatch):
    for key in ("COST_SOURCE", "REPOSITORY", "DB_HOST", "DB_SSLMODE", "COLLECT_DAYS"):
        monkeypatch.delenv(key, raising=False)
    s = Settings.from_env()
    assert (s.cost_source, s.repository, s.db_host, s.db_sslmode, s.collect_days) == (
        "mock", "postgres", "localhost", "prefer", 3)


def test_from_env(monkeypatch):
    monkeypatch.setenv("COST_SOURCE", "AWS")
    monkeypatch.setenv("DB_HOST", "mydb.xxxx.ap-northeast-2.rds.amazonaws.com")
    monkeypatch.setenv("DB_PORT", "6543")
    monkeypatch.setenv("DB_SSLMODE", "require")
    monkeypatch.setenv("COLLECT_DAYS", "7")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    s = Settings.from_env()
    assert s.cost_source == "aws"
    assert s.db_port == 6543 and s.collect_days == 7 and s.log_level == "DEBUG"
    params = conninfo_to_dict(s.db_conninfo)
    assert params["host"].endswith("rds.amazonaws.com")
    assert params["sslmode"] == "require"


def test_conninfo_escapes_special_chars():
    s = Settings(db_password="p@ss word'=x")
    assert conninfo_to_dict(s.db_conninfo)["password"] == "p@ss word'=x"


def test_empty_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DB_HOST", "")
    assert Settings.from_env().db_host == "localhost"


@pytest.mark.parametrize("field,value", [("cost_source", "gcp"), ("repository", "mysql")])
def test_unknown_backends_rejected(field, value):
    from app.clients.cost_explorer import build_cost_explorer_client
    from app.repositories.cost_repository import build_cost_repository

    s = Settings(**{field: value})
    builder = build_cost_explorer_client if field == "cost_source" else build_cost_repository
    with pytest.raises(ValueError):
        builder(s)


def test_postgres_requires_password():
    from app.repositories.cost_repository import PostgresCostRepository

    with pytest.raises(ValueError, match="DB_PASSWORD"):
        PostgresCostRepository(Settings(repository="postgres", db_password=""))
