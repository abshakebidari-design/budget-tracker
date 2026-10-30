# Budget Tracker

A full-stack budgeting app built with **Python, FastAPI and SQLite**. Record income and expenses, set a monthly budget per category, and see at a glance where your money went and which categories are over budget.

![Tests](https://github.com/abshakebidari-design/budget-tracker/actions/workflows/tests.yml/badge.svg)

## Features

- **REST API** with full create, read, update and delete for transactions
- **Filtering and pagination**: by month, type (income/expense) and category, newest first
- **Monthly budgets** per category, with a summary showing spent, remaining and over-budget categories
- **Monthly summary**: total income, expenses and balance, computed in SQL with `GROUP BY` and `JOIN`s
- **Input validation** with Pydantic: positive amounts, real dates, cleaned-up category names
- **Web dashboard** (plain HTML, CSS and JavaScript) that calls the API, with spending bars per category
- **Interactive API docs** generated automatically at `/docs`
- **22 automated tests** with pytest, run on every push by GitHub Actions

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic |
| Database | SQLite (Python's built-in `sqlite3`, parameterized SQL) |
| Frontend | HTML, CSS, vanilla JavaScript (`fetch`) |
| Testing | pytest, FastAPI TestClient |
| CI | GitHub Actions |

## Run it locally

```bash
git clone https://github.com/abshakebidari-design/budget-tracker.git
cd budget-tracker
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

- **Dashboard:** http://127.0.0.1:8000/
- **API docs:** http://127.0.0.1:8000/docs

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/transactions` | Add a transaction |
| `GET` | `/api/transactions` | List transactions (`month`, `type`, `category`, `limit`, `offset`) |
| `GET` | `/api/transactions/{id}` | Get one transaction |
| `PUT` | `/api/transactions/{id}` | Update a transaction |
| `DELETE` | `/api/transactions/{id}` | Delete a transaction |
| `GET` | `/api/budgets` | List monthly budgets |
| `PUT` | `/api/budgets/{category}` | Create or update a category's monthly budget |
| `DELETE` | `/api/budgets/{category}` | Remove a budget |
| `GET` | `/api/summary?month=YYYY-MM` | Income, expenses, balance and per-category spending vs. budget |

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{"type": "expense", "amount": 42.50, "category": "groceries", "date": "2026-10-06", "note": "Walmart"}'
```

## Tests

```bash
pytest -v
```

The tests use a fresh temporary database for every test. They cover validation errors, 404s, filters, pagination, budget upserts, the monthly summary math, SQL-injection attempts, and parallel requests.

## Project structure

```
app/
  main.py         API routes and the summary query
  database.py     SQLite connection and table schema
  schemas.py      Pydantic request/response models and validation
  static/
    index.html    Dashboard
tests/
  test_api.py     pytest suite
```

## Design notes

- **One database connection per request**, opened and closed by a FastAPI dependency, so requests never share state.
- **All SQL uses parameters** (`?`), never string formatting, which prevents SQL injection. A test checks this.
- **Money is rounded to cents** on the way in, and amounts are always positive; the `type` field says whether it is income or an expense.
- The summary includes categories that have a budget but no spending yet, so you can see your full plan for the month.

## Ideas for future work

- User accounts with login, so several people can keep separate budgets
- Recurring transactions (rent, subscriptions)
- Charts of spending over several months
- CSV import from a bank statement
