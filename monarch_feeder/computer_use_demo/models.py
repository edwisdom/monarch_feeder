"""
Standalone models for computer use automation.
This module is self-contained and doesn't depend on the larger monarch_feeder package.
"""

import datetime
from collections import namedtuple

from pydantic import BaseModel, field_validator

# Define namedtuple for holding data
HoldingData = namedtuple("HoldingData", ["shares", "holding_id"])


class Transaction(BaseModel):
    """Pydantic model for transaction validation and serialization."""

    date: str
    user_account: str
    counterparty_account: str
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


class Holding(BaseModel):
    """Individual portfolio holding with stock ticker and share count."""

    stock_ticker: str
    shares: float
    holding_id: str | None = None

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

    def to_dict(self) -> dict[str, HoldingData]:
        """Convert this Holding to a dict keyed on stock_ticker.

        Returns:
            Dict with stock_ticker as key and HoldingData namedtuple as value
        """
        return {
            self.stock_ticker: HoldingData(
                shares=self.shares, holding_id=self.holding_id
            )
        }


class Portfolio(BaseModel):
    """Portfolio containing a list of holdings."""

    holdings: list[Holding]

    @field_validator("holdings")
    @classmethod
    def validate_no_duplicate_tickers(cls, v):
        """Ensure no stock ticker is repeated in the portfolio."""
        tickers = [holding.stock_ticker.upper() for holding in v]
        if len(tickers) != len(set(tickers)):
            duplicates = [
                ticker for ticker in set(tickers) if tickers.count(ticker) > 1
            ]
            raise ValueError(f"Duplicate stock tickers found: {duplicates}")
        return v

    def get_total_positions(self) -> int:
        """Return the total number of different positions."""
        return len(self.holdings)

    def get_holding_by_ticker(self, ticker: str) -> Holding | None:
        """Get a specific holding by ticker symbol."""
        for holding in self.holdings:
            if holding.stock_ticker == ticker.upper():
                return holding
        return None

    def to_dict(self) -> dict[str, HoldingData]:
        """Convert all holdings to a single dict with stock tickers as keys.

        Returns:
            Dict with stock_ticker as keys and HoldingData namedtuples as values
        """
        result = {}
        for holding in self.holdings:
            result.update(holding.to_dict())
        return result
