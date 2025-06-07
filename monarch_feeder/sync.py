import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from monarchmoney import MonarchMoney

from monarch_feeder.computer_use_demo.automation_orchestrator import (
    DEFAULT_OUTPUT_DIR,
    AutomationType,
)
from monarch_feeder.computer_use_demo.models import (
    Portfolio,
    TransactionLog,
    get_transaction_log_diff,
)
from monarch_feeder.monarch import (
    add_transaction_to_account,
    login,
    update_account_holdings,
)


class SyncType(Enum):
    TRANSACTIONS = "transactions"
    PORTFOLIO = "portfolio"


@dataclass
class SyncConfig:
    name: str
    type: SyncType
    automation_type: AutomationType
    subtask_name: str
    account_id: str
    category_id: str | None = None
    update_balance: bool = False

    def get_pattern(self) -> str:
        return f"{DEFAULT_OUTPUT_DIR}/{self.automation_type.value}/{self.subtask_name}/*.json"


SYNC_CONFIGS = [
    SyncConfig(
        name="Human Interest Transactions",
        type=SyncType.TRANSACTIONS,
        automation_type=AutomationType.HUMAN_INTEREST,
        subtask_name="transactions",
        account_id=os.getenv("MONARCH_HUMAN_INTEREST_ACCOUNT_ID"),
        category_id=os.getenv("MONARCH_HUMAN_INTEREST_CATEGORY_ID"),
        update_balance=False,
    ),
    SyncConfig(
        name="Human Interest Portfolio",
        type=SyncType.PORTFOLIO,
        automation_type=AutomationType.HUMAN_INTEREST,
        subtask_name="portfolio",
        account_id=os.getenv("MONARCH_HUMAN_INTEREST_ACCOUNT_ID"),
        update_balance=False,
    ),
    SyncConfig(
        name="Rippling HSA Transactions",
        type=SyncType.TRANSACTIONS,
        automation_type=AutomationType.RIPPLING,
        subtask_name="hsa_transactions",
        account_id=os.getenv("MONARCH_ELEVATE_UMB_ACCOUNT_ID"),
        category_id=os.getenv("MONARCH_ELEVATE_UMB_CATEGORY_ID"),
        update_balance=False,
    ),
    SyncConfig(
        name="Rippling HSA Portfolio",
        type=SyncType.PORTFOLIO,
        automation_type=AutomationType.RIPPLING,
        subtask_name="hsa_portfolio",
        account_id=os.getenv("MONARCH_ELEVATE_UMB_ACCOUNT_ID"),
        update_balance=False,
    ),
    SyncConfig(
        name="Rippling Commuter Benefits",
        type=SyncType.TRANSACTIONS,
        automation_type=AutomationType.RIPPLING,
        subtask_name="commuter_benefits",
        account_id=os.getenv("MONARCH_RIPPLING_COMMUTER_ACCOUNT_ID"),
        category_id=os.getenv("MONARCH_RIPPLING_COMMUTER_CATEGORY_ID"),
        update_balance=True,
    ),
]


def extract_datetime_from_filename(filepath: str) -> datetime:
    """Extract datetime from filename with format ..._{yyyymmdd}_{hhmmss}.json"""
    filename = Path(filepath).name
    # Match the pattern _{yyyymmdd}_{hhmmss}.json at the end of filename
    match = re.search(r"_(\d{8})_(\d{6})\.json$", filename)

    # Fallback to modification time if pattern doesn't match
    if not match:
        return datetime.fromtimestamp(os.path.getmtime(filepath))

    date_str, time_str = match.groups()
    return datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")


def get_latest_files(pattern: str, n: int) -> list[Path]:
    """Get the n most recent files matching the pattern based on filename datetime."""
    pattern_path = Path(pattern)
    parent_dir = pattern_path.parent
    file_pattern = pattern_path.name

    return sorted(
        parent_dir.glob(file_pattern),
        key=lambda p: extract_datetime_from_filename(str(p)),
        reverse=True,
    )[:n]


async def sync_transactions_to_monarch(
    mm: MonarchMoney, config: SyncConfig, dry_run: bool = False
) -> None:
    """Sync transactions to Monarch Money."""
    pattern = config.get_pattern()
    files = get_latest_files(pattern, 2)

    if not files:
        raise ValueError(f"No files found for {config.name} at {pattern}")

    new_log = TransactionLog.from_json_file(files[0])
    old_log = TransactionLog.from_json_file(files[1]) if len(files) > 1 else []
    diff_log = get_transaction_log_diff(new_log, old_log)

    for transaction in diff_log.transactions:
        if dry_run:
            print(
                f"🔍 Would add: {transaction.date} - {transaction.counterparty_account} - ${transaction.amount}"
            )
        else:
            success = await add_transaction_to_account(
                mm,
                transaction,
                config.account_id,
                config.category_id,
                update_balance=config.update_balance,
            )
            if not success:
                print(
                    f"❌ Failed to add: {transaction.date} - {transaction.counterparty_account}"
                )


async def sync_portfolio_to_monarch(
    mm: MonarchMoney, config: SyncConfig, dry_run: bool = False
) -> None:
    """Sync portfolio to Monarch Money."""
    pattern = config.get_pattern()
    files = get_latest_files(pattern, 1)

    if not files:
        raise ValueError(f"No files found for {config.name} at {pattern}")

    portfolio = Portfolio.from_json_file(files[0])

    if dry_run:
        print(f"🔍 Would sync portfolio with {len(portfolio.holdings)} holdings:")
        for holding in portfolio.holdings:
            print(f"   - {holding.stock_ticker}: {holding.shares} shares")
    else:
        success = await update_account_holdings(mm, config.account_id, portfolio)
        if not success:
            print(f"❌ Failed to sync portfolio for {config.name}")


async def sync_data_to_monarch(dry_run: bool = False) -> None:
    """Sync data to Monarch Money."""
    mm = await login()

    for config in SYNC_CONFIGS:
        match config.type:
            case SyncType.TRANSACTIONS:
                await sync_transactions_to_monarch(mm, config, dry_run)
            case SyncType.PORTFOLIO:
                await sync_portfolio_to_monarch(mm, config, dry_run)

    print("✅ Sync complete")
