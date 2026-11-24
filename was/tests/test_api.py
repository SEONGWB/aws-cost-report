from __future__ import annotations


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz(client):
    assert client.get("/readyz").json() == {"status": "ready"}


def test_readyz_db_down(client, repository, monkeypatch):
    monkeypatch.setattr(repository, "ping", lambda: False)
    r = client.get("/readyz")
    assert r.status_code == 503


def test_api_db_down_returns_json_503(client, repository, monkeypatch):
    import psycopg

    def boom(*_a, **_k):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(repository, "latest_date", boom)
    r = client.get("/api/meta")
    assert r.status_code == 503
    assert r.json() == {"detail": "database unavailable"}
    assert r.headers["retry-after"] == "10"


def test_meta(client, seeded):
    body = client.get("/api/meta").json()
    assert body["cost_source"] == "mock"
    assert body["repository"] == "memory"
    assert body["latest_date"] == "2026-11-15"


def test_daily_report(client, seeded):
    body = client.get("/api/costs/daily", params={"date": "2026-11-15"}).json()
    assert body["date"] == "2026-11-15"
    assert body["has_data"] is True
    assert body["currency"] == "USD"
    assert len(body["services"]) == 8
    amounts = [s["amount"] for s in body["services"]]
    assert amounts == sorted(amounts, reverse=True)
    # 서비스별 반올림 오차 허용 (8개 x 최대 0.005)
    assert abs(sum(amounts) - body["total"]) <= 0.04 + 1e-9
    # 증감은 화면에 보이는 숫자끼리 정확히 일치해야 한다
    assert round(body["total"] - body["prev_total"], 2) == body["change"]
    for s in body["services"]:
        assert round(s["amount"] - s["prev_amount"], 2) == s["change"]
    assert body["month_to_date"] > body["total"]


def test_daily_report_no_data(client):
    body = client.get("/api/costs/daily", params={"date": "2020-01-01"}).json()
    assert body["has_data"] is False
    assert body["total"] == 0
    assert body["services"] == []
    assert body["change_pct"] is None


def test_daily_bad_date(client):
    assert client.get("/api/costs/daily", params={"date": "bad"}).status_code == 422


def test_trend(client, seeded):
    body = client.get("/api/costs/trend", params={"days": 7, "end": "2026-11-15"}).json()
    dates = [p["date"] for p in body["points"]]
    assert dates == [f"2026-11-{d:02d}" for d in range(9, 16)]
    assert all(p["total"] > 0 for p in body["points"])


def test_trend_days_validation(client):
    assert client.get("/api/costs/trend", params={"days": 0}).status_code == 422
    assert client.get("/api/costs/trend", params={"days": 91}).status_code == 422
