"""SQLite storage for transactions and monthly budgets.

Each request opens its own connection (see get_db in main.py), which keeps the
code simple and safe with FastAPI's threaded request handling.
"""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    type     TEXT    NOT NULL CHECK (type IN ('income', 'expense')),
    amount   REAL    NOT NULL CHECK (amount > 0),
    category TEXT    NOT NULL,
    date     TEXT    NOT NULL,          -- ISO date, e.g. 2026-10-30
    note     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date);

CREATE TABLE IF NOT EXISTS budgets (
    category      TEXT PRIMARY KEY,
    monthly_limit REAL NOT NULL CHECK (monthly_limit > 0)
);
"""


def db_path() -> str:
    """Database file location. Tests point BUDGET_DB at a temporary file."""
    return os.environ.get("BUDGET_DB", "budget.db")


def connect() -> sqlite3.Connection:
    # FastAPI may open the connection in one worker thread and run the endpoint in
    # another. That's safe here because each request gets its own connection and
    # never shares it, so we turn off sqlite3's same-thread check.
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
