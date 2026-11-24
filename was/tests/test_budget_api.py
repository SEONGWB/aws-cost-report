"""월 예산 등록 · 조회 · 수정 API."""
from __future__ import annotations

EC2 = "Amazon Elastic Compute Cloud - Compute"


def _create(client, **over):
    body = {"month": "2026-11", "service": EC2, "amount": 300} | over
    return client.post("/api/budgets", json=body)


def test_create_get_update_flow(client, seeded):
    r = _create(client)
    assert r.status_code == 201
    created = r.json()
    assert created["month"] == "2026-11" and created["amount"] == 300
    assert created["spent"] > 0                       # 11월 1~15일 mock 사용액
    assert created["usage_pct"] == round(created["spent"] / 300 * 100, 1)

    got = client.get(f"/api/budgets/{created['id']}").json()
    assert got == created

    r = client.put(f"/api/budgets/{created['id']}", json={"amount": 500})
    assert r.status_code == 200
    assert r.json()["amount"] == 500 and r.json()["spent"] == created["spent"]

    listed = client.get("/api/budgets", params={"month": "2026-11"}).json()
    assert [b["amount"] for b in listed] == [500]


def test_duplicate_is_409(client):
    assert _create(client).status_code == 201
    assert _create(client, amount=10).status_code == 409


def test_not_found_is_404(client):
    assert client.get("/api/budgets/999").status_code == 404
    assert client.put("/api/budgets/999", json={"amount": 1}).status_code == 404


def test_validation_is_422(client):
    assert _create(client, amount=0).status_code == 422
    assert _create(client, month="2026-13").status_code == 422
    assert _create(client, service="").status_code == 422
    assert client.get("/api/budgets", params={"month": "11-2026"}).status_code == 422


def test_list_is_per_month(client):
    _create(client, month="2026-10")
    _create(client, month="2026-11", service="Amazon Simple Storage Service")
    assert [b["month"] for b in client.get("/api/budgets?month=2026-10").json()] == ["2026-10"]


def test_no_spend_means_zero_pct(client):
    b = _create(client, month="2027-01").json()
    assert b["spent"] == 0 and b["usage_pct"] == 0
