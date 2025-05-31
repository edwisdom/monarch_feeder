"""
Standalone models for computer use automation.
This module is self-contained and doesn't depend on the larger monarch_feeder package.
"""

import datetime

from pydantic import BaseModel, field_validator


class TransactionModel(BaseModel):
    """Pydantic model for transaction validation and serialization."""

    date: str
    from_account: str
    to_account: str
    description: str
    amount: float

    @field_validator("date")
    @classmethod
    def validate_date(cls, v):
        """Ensure date is in YYYY-MM-DD format and is a valid date."""
        try:
            datetime.datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @field_validator("from_account", "to_account", "description")
    @classmethod
    def validate_non_empty_string(cls, v):
        """Ensure string fields are not empty and normalize whitespace."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        """Ensure amount is positive."""
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v


class Holding(BaseModel):
    """Individual portfolio holding with stock ticker and share count."""

    stock_ticker: str
    shares: float

    @field_validator("stock_ticker")
    @classmethod
    def validate_ticker(cls, v):
        """Ensure stock ticker is uppercase and alphanumeric."""
        if not v.isalpha():
            raise ValueError("Stock ticker must contain only letters")
        return v.upper()

    @field_validator("shares")
    @classmethod
    def validate_shares(cls, v):
        """Ensure shares is positive."""
        if v <= 0:
            raise ValueError("Shares must be positive")
        return v


class Portfolio(BaseModel):
    """Portfolio containing a list of holdings."""

    holdings: list[Holding]

    def get_total_positions(self) -> int:
        """Return the total number of different positions."""
        return len(self.holdings)

    def get_holding_by_ticker(self, ticker: str) -> Holding | None:
        """Get a specific holding by ticker symbol."""
        for holding in self.holdings:
            if holding.stock_ticker == ticker.upper():
                return holding
        return None
