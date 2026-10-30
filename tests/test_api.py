"""API tests. Run with:  pytest"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Every test gets its own empty database file.
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:  # "with" runs startup, which creates the tables
        yield c


def add(client, type="expense", amount=10.0, category="food", date="2026-10-05", note=""):
    res = client.post("/api/transactions", json={
        "type": type, "amount": amount, "category": category, "date": date, "note": note})
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------------------------------------ transactions

def test_create_and_get_transaction(client):
    tx = add(client, amount=12.5, note="lunch")
    assert tx["id"] > 0
    assert client.get(f"/api/transactions/{tx['id']}").json() == tx


def test_category_is_normalized(client):
    assert add(client, category="  Food ")["category"] == "food"


def test_amount_is_rounded_to_cents(client):
    assert add(client, amount=10.129)["amount"] == 10.13


@pytest.mark.parametrize("bad", [
    {"amount": 0},
    {"amount": -5},
    {"type": "transfer"},
    {"category": "   "},
    {"date": "2026-13-01"},
    {"date": "not a date"},
])
def test_invalid_transactions_are_rejected(client, bad):
    body = {"type": "expense", "amount": 10, "category": "food", "date": "2026-10-05", **bad}
    assert client.post("/api/transactions", json=body).status_code == 422


def test_missing_transaction_returns_404(client):
    assert client.get("/api/transactions/999").status_code == 404
    assert client.delete("/api/transactions/999").status_code == 404
    body = {"type": "expense", "amount": 1, "category": "x", "date": "2026-10-01"}
    assert client.put("/api/transactions/999", json=body).status_code == 404


def test_update_transaction(client):
    tx = add(client)
    body = {"type": "income", "amount": 99, "category": "salary", "date": "2026-10-31", "note": "pay"}
    updated = client.put(f"/api/transactions/{tx['id']}", json=body).json()
    assert updated == {"id": tx["id"], **body}


def test_delete_transaction(client):
    tx = add(client)
    assert client.delete(f"/api/transactions/{tx['id']}").status_code == 204
    assert client.get(f"/api/transactions/{tx['id']}").status_code == 404


def test_list_filters(client):
    add(client, category="food", date="2026-10-01")
    add(client, category="rent", date="2026-10-02")
    add(client, type="income", category="salary", date="2026-10-03")
    add(client, category="food", date="2026-09-30")

    def ids(**params):
        return len(client.get("/api/transactions", params=params).json())

    assert ids() == 4
    assert ids(month="2026-10") == 3
    assert ids(type="income") == 1
    assert ids(category="FOOD") == 2
    assert ids(category="food", month="2026-10") == 1


def test_list_is_newest_first_and_paginated(client):
    for day in range(1, 6):
        add(client, date=f"2026-10-0{day}")
    page = client.get("/api/transactions", params={"limit": 2, "offset": 1}).json()
    assert [t["date"] for t in page] == ["2026-10-04", "2026-10-03"]


def test_bad_month_filter_is_rejected(client):
    assert client.get("/api/transactions", params={"month": "2026-1"}).status_code == 422


def test_filter_values_cannot_inject_sql(client):
    add(client)
    res = client.get("/api/transactions", params={"category": "food' OR '1'='1"})
    assert res.status_code == 200 and res.json() == []


# ----------------------------------------------------------------- budgets

def test_set_update_and_delete_budget(client):
    assert client.put("/api/budgets/Food", json={"monthly_limit": 200}).json() == {
        "category": "food", "monthly_limit": 200}
    client.put("/api/budgets/food", json={"monthly_limit": 250})  # update, not duplicate
    assert client.get("/api/budgets").json() == [{"category": "food", "monthly_limit": 250}]
    assert client.delete("/api/budgets/food").status_code == 204
    assert client.get("/api/budgets").json() == []


def test_budget_must_be_positive(client):
    assert client.put("/api/budgets/food", json={"monthly_limit": 0}).status_code == 422


# ----------------------------------------------------------------- summary

def test_summary_totals_and_budgets(client):
    add(client, type="income", amount=2000, category="salary", date="2026-10-01")
    add(client, amount=120.25, category="food", date="2026-10-03")
    add(client, amount=80, category="food", date="2026-10-20")
    add(client, amount=900, category="rent", date="2026-10-01")
    add(client, amount=500, category="rent", date="2026-09-01")  # other month, ignored
    client.put("/api/budgets/food", json={"monthly_limit": 150})
    client.put("/api/budgets/travel", json={"monthly_limit": 300})

    s = client.get("/api/summary", params={"month": "2026-10"}).json()
    assert (s["income"], s["expenses"], s["balance"]) == (2000, 1100.25, 899.75)

    cats = {c["category"]: c for c in s["categories"]}
    assert [c["category"] for c in s["categories"]] == ["rent", "food", "travel"]  # biggest first
    assert cats["food"] == {"category": "food", "spent": 200.25, "budget": 150,
                            "remaining": -50.25, "over_budget": True}
    assert cats["rent"]["budget"] is None and cats["rent"]["over_budget"] is False
    assert cats["travel"]["spent"] == 0 and cats["travel"]["remaining"] == 300


def test_summary_for_empty_month(client):
    s = client.get("/api/summary", params={"month": "2020-01"}).json()
    assert s == {"month": "2020-01", "income": 0, "expenses": 0, "balance": 0, "categories": []}


def test_parallel_requests(client):
    # The dashboard fires several requests at once; each must get a working connection.
    from concurrent.futures import ThreadPoolExecutor

    add(client)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: client.get("/api/summary?month=2026-10").status_code, range(40)))
    assert codes == [200] * 40


def test_dashboard_is_served(client):
    res = client.get("/")
    assert res.status_code == 200 and "Budget Tracker" in res.text
