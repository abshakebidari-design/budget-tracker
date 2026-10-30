"""Request and response shapes. Pydantic validates every request body."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TransactionIn(BaseModel):
    type: Literal["income", "expense"]
    amount: float = Field(gt=0, description="Always positive; `type` gives the sign")
    category: str = Field(min_length=1, max_length=40)
    date: date
    note: str = Field(default="", max_length=200)

    @field_validator("category")
    @classmethod
    def clean_category(cls, value: str) -> str:
        # "  Food " and "food" should count as the same category
        value = value.strip().lower()
        if not value:
            raise ValueError("category cannot be blank")
        return value


class Transaction(TransactionIn):
    id: int


class BudgetIn(BaseModel):
    monthly_limit: float = Field(gt=0)


class Budget(BudgetIn):
    category: str


class CategorySummary(BaseModel):
    category: str
    spent: float
    budget: float | None = None
    remaining: float | None = None
    over_budget: bool = False


class Summary(BaseModel):
    month: str
    income: float
    expenses: float
    balance: float
    categories: list[CategorySummary]
