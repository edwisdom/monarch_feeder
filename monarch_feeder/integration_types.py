"""Type definitions for the sync system."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from monarch_feeder.financial_models import Portfolio, Transaction, TransactionLog

# Type variable for platform-specific data
T = TypeVar("T")


class Platform(Enum):
    """Supported financial platforms."""

    HUMAN_INTEREST = "human_interest"
    RIPPLING = "rippling"
    HSA_BANK = "hsa_bank"
    NAVIA = "navia"


class StreamType(Enum):
    """Type of data stream."""

    TRANSACTIONS = "transactions"
    PORTFOLIO = "portfolio"


@dataclass
class DataStream(Generic[T]):
    """Data stream that extracts and syncs specific data from a platform.

    Generic over T, the type of platform data this stream extracts from.
    """

    name: str
    stream_type: StreamType
    account_id: str
    account_name: str
    extractor: Callable[[T], TransactionLog | Portfolio]
    category_id: str | None = None
    # Category for money leaving the account, e.g. card swipes, when it should
    # be filed apart from money coming in. Defaults to category_id.
    spending_category_id: str | None = None
    update_balance: bool = False

    def category_for(self, transaction: Transaction) -> str | None:
        """Return the Monarch category a transaction should be filed under."""
        if transaction.amount < 0 and self.spending_category_id:
            return self.spending_category_id
        return self.category_id


@dataclass
class Integration(Generic[T]):
    """Integration with a financial platform.

    Generic over T, the type of data this integration fetches.
    Each integration fetches data once and feeds it to all its data streams.
    """

    name: str
    data_fetcher: Callable[[], T]
    data_streams: list[DataStream[T]]
