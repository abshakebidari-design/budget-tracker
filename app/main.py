"""Budget Tracker API.

Run locally:  uvicorn app.main:app --reload
Dashboard:    http://127.0.0.1:8000/
API docs:     http://127.0.0.1:8000/docs
"""
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse

from . import database
from .schemas import Budget, BudgetIn, CategorySummary, Summary, Transaction, TransactionIn

STATIC = Path(__file__).parent / "static"
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()  # create tables on startup
    yield


app = FastAPI(title="Budget Tracker API", version="1.0.0", lifespan=lifespan)


def get_db() -> Iterator[sqlite3.Connection]:
    """One connection per request, committed if the request succeeds."""
    conn = database.connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def check_month(month: str) -> str:
    if not MONTH.match(month):
        raise HTTPException(422, "month must look like YYYY-MM")
    return month


def row_to_transaction(row: sqlite3.Row) -> Transaction:
    return Transaction(**dict(row))


# ---------------------------------------------------------------- dashboard

@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC / "index.html")


# ------------------------------------------------------------- transactions

@app.post("/api/transactions", response_model=Transaction, status_code=201)
def create_transaction(tx: TransactionIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO transactions (type, amount, category, date, note) VALUES (?, ?, ?, ?, ?)",
        (tx.type, round(tx.amount, 2), tx.category, tx.date.isoformat(), tx.note),
    )
    return Transaction(id=cur.lastrowid, **tx.model_dump(exclude={"amount"}), amount=round(tx.amount, 2))


@app.get("/api/transactions", response_model=list[Transaction])
def list_transactions(
    type: Literal["income", "expense"] | None = None,
    category: str | None = None,
    month: str | None = Query(None, description="YYYY-MM"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    # Build the WHERE clause from whichever filters were given.
    # Values are always passed as parameters, never pasted into the SQL (prevents SQL injection).
    where, params = [], []
    if type:
        where.append("type = ?")
        params.append(type)
    if category:
        where.append("category = ?")
        params.append(category.strip().lower())
    if month:
        where.append("substr(date, 1, 7) = ?")
        params.append(check_month(month))
    sql = "SELECT * FROM transactions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    rows = db.execute(sql, [*params, limit, offset]).fetchall()
    return [row_to_transaction(r) for r in rows]


@app.get("/api/transactions/{tx_id}", response_model=Transaction)
def get_transaction(tx_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "transaction not found")
    return row_to_transaction(row)


@app.put("/api/transactions/{tx_id}", response_model=Transaction)
def update_transaction(tx_id: int, tx: TransactionIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "UPDATE transactions SET type = ?, amount = ?, category = ?, date = ?, note = ? WHERE id = ?",
        (tx.type, round(tx.amount, 2), tx.category, tx.date.isoformat(), tx.note, tx_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "transaction not found")
    return get_transaction(tx_id, db)


@app.delete("/api/transactions/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "transaction not found")
    return Response(status_code=204)


# ------------------------------------------------------------------ budgets

@app.get("/api/budgets", response_model=list[Budget])
def list_budgets(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT category, monthly_limit FROM budgets ORDER BY category").fetchall()
    return [Budget(**dict(r)) for r in rows]


@app.put("/api/budgets/{category}", response_model=Budget)
def set_budget(category: str, body: BudgetIn, db: sqlite3.Connection = Depends(get_db)):
    category = category.strip().lower()
    # "Upsert": insert the budget, or update it if the category already has one.
    db.execute(
        "INSERT INTO budgets (category, monthly_limit) VALUES (?, ?) "
        "ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
        (category, round(body.monthly_limit, 2)),
    )
    return Budget(category=category, monthly_limit=round(body.monthly_limit, 2))


@app.delete("/api/budgets/{category}", status_code=204)
def delete_budget(category: str, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM budgets WHERE category = ?", (category.strip().lower(),))
    if cur.rowcount == 0:
        raise HTTPException(404, "budget not found")
    return Response(status_code=204)


# ------------------------------------------------------------------ summary

@app.get("/api/summary", response_model=Summary)
def monthly_summary(
    month: str = Query(default_factory=lambda: date.today().strftime("%Y-%m"), description="YYYY-MM"),
    db: sqlite3.Connection = Depends(get_db),
):
    check_month(month)
    totals = db.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN type = 'income'  THEN amount END), 0) AS income,
             COALESCE(SUM(CASE WHEN type = 'expense' THEN amount END), 0) AS expenses
           FROM transactions WHERE substr(date, 1, 7) = ?""",
        (month,),
    ).fetchone()

    # Spending per category, joined with any budget set for it. Categories that
    # have a budget but no spending yet still appear (spent = 0).
    rows = db.execute(
        """SELECT c.category,
                  COALESCE(s.spent, 0) AS spent,
                  b.monthly_limit      AS budget
           FROM (SELECT category FROM budgets
                 UNION
                 SELECT category FROM transactions
                 WHERE type = 'expense' AND substr(date, 1, 7) = ?) AS c
           LEFT JOIN (SELECT category, SUM(amount) AS spent FROM transactions
                      WHERE type = 'expense' AND substr(date, 1, 7) = ?
                      GROUP BY category) AS s ON s.category = c.category
           LEFT JOIN budgets AS b ON b.category = c.category
           ORDER BY spent DESC, c.category""",
        (month, month),
    ).fetchall()

    categories = []
    for r in rows:
        spent = round(r["spent"], 2)
        budget = r["budget"]
        categories.append(
            CategorySummary(
                category=r["category"],
                spent=spent,
                budget=budget,
                remaining=None if budget is None else round(budget - spent, 2),
                over_budget=budget is not None and spent > budget,
            )
        )

    income, expenses = round(totals["income"], 2), round(totals["expenses"], 2)
    return Summary(
        month=month,
        income=income,
        expenses=expenses,
        balance=round(income - expenses, 2),
        categories=categories,
    )
