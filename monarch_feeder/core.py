import datetime
import typing
from dataclasses import dataclass

FUND: typing.TypeAlias = str
INVESTMENTS: typing.TypeAlias = dict[FUND, float]
ACCOUNT: typing.TypeAlias = str


@dataclass
class Transaction:
    date: datetime.date
    amount: float
    from_account: ACCOUNT
    to_account: ACCOUNT
    description: str | None = None
