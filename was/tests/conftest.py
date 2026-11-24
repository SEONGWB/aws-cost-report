from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.application import Application
from app.clients.cost_explorer import MockCostExplorerClient
from app.config import Settings
from app.repositories.cost_repository import InMemoryCostRepository


@pytest.fixture
def settings() -> Settings:
    return Settings(cost_source="mock", repository="memory")


@pytest.fixture
def repository() -> InMemoryCostRepository:
    return InMemoryCostRepository()


@pytest.fixture
def application(settings, repository) -> Application:
    return Application(settings=settings, client=MockCostExplorerClient(), repository=repository)


@pytest.fixture
def client(application) -> TestClient:
    with TestClient(application.api) as c:
        yield c


@pytest.fixture
def seeded(application) -> Application:
    """2026-10-01 ~ 2026-11-15 (46일) 가짜 데이터 적재."""
    application.service.collect(date(2026, 10, 1), date(2026, 11, 16))
    return application
