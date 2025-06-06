"""
Standalone models for computer use automation.
This module is self-contained and doesn't depend on the larger monarch_feeder package.
"""

import datetime
import json
from collections import defaultdict, namedtuple
from pathlib import Path

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

    def __hash__(self):
        return hash(
            (self.date, self.user_account, self.counterparty_account, self.amount)
        )


class TransactionLog(BaseModel):
    """Log of transactions."""

    transactions: list[Transaction]

    @field_validator("transactions")
    @classmethod
    def validate_transactions(cls, v):
        """Ensure there are no duplicate transactions."""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate transactions found")
        return v

    @classmethod
    def from_json_file(cls, json_file: Path) -> "TransactionLog":
        """Create a TransactionLog from a JSON file containing a list of transactions."""
        with open(json_file, "r") as f:
            transactions_data = json.load(f)
        transactions = [
            Transaction(**transaction_dict) for transaction_dict in transactions_data
        ]
        return cls(transactions=transactions)


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

    @classmethod
    def from_json_file(cls, json_file: Path) -> "Portfolio":
        """Create a Portfolio from a JSON file containing a list of holdings."""
        with open(json_file, "r") as f:
            holdings_data = json.load(f)

        # Create Holding objects from the list
        holdings = [Holding(**holding_dict) for holding_dict in holdings_data]

        return cls(holdings=holdings)


def get_transaction_log_diff(
    new_log: list[Transaction], old_log: list[Transaction]
) -> list[Transaction]:
    """Reconcile two lists of transactions.

    Returns transactions that are in new_log but not in old_log.
    Groups by (date, amount) and compares counts.

    Note that this doesn't handle the edge case where the new logs have
    more transactions of a certain amount on a given date than the old log.
    In that case, we'd need to use some kind of matching algorithm (e.g. an LLM)
    to determine which transactions are new and which are old. This seems
    unnecessary in 99.99% of cases for this application, so it hasn't been implemented.
    """
    # Group transactions by (date, amount)
    new_groups = defaultdict(list)
    old_groups = defaultdict(list)

    for transaction in new_log:
        key = (transaction.date, transaction.amount)
        new_groups[key].append(transaction)

    for transaction in old_log:
        key = (transaction.date, transaction.amount)
        old_groups[key].append(transaction)

    new_transactions = []

    # For each (date, amount) group in new_log
    for key, new_group in new_groups.items():
        old_group = old_groups.get(key, [])

        new_count = len(new_group)
        old_count = len(old_group)

        if new_count > old_count:
            # Add the excess transactions as new
            excess_count = new_count - old_count
            new_transactions.extend(new_group[:excess_count])

    return new_transactions
