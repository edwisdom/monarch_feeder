"""Sync financial data from external platforms to Monarch Money."""

from monarchmoney import MonarchMoney

from monarch_feeder.computer_use_demo.models import Portfolio, TransactionLog
from monarch_feeder.integration_types import (
    DataStream,
    Integration,
    Platform,
    StreamType,
)
from monarch_feeder.integrations import INTEGRATIONS
from monarch_feeder.monarch import (
    add_transaction_to_account,
    get_transactions_for_account,
    login,
    update_account_holdings,
)


async def _sync_transactions(
    mm: MonarchMoney,
    stream: DataStream,
    transactions: TransactionLog,
    dry_run: bool,
) -> None:
    """Sync transactions by comparing scraped data with Monarch data."""
    monarch_transactions = await get_transactions_for_account(
        mm, stream.account_id, stream.account_name
    )
    new_transactions = transactions - monarch_transactions

    if not new_transactions.transactions:
        print(f"  ✓ {stream.name}: No new transactions")
        return

    for txn in new_transactions.transactions:
        if dry_run:
            print(
                f"    🔍 Would add: {txn.date} | {txn.counterparty_account} | ${txn.amount:.2f}"
            )
        else:
            success = await add_transaction_to_account(
                mm, txn, stream.account_id, stream.category_id, stream.update_balance
            )
            status = "✓" if success else "❌"
            print(
                f"    {status} {txn.date} | {txn.counterparty_account} | ${txn.amount:.2f}"
            )


async def _sync_portfolio(
    mm: MonarchMoney,
    stream: DataStream,
    portfolio: Portfolio,
    dry_run: bool,
) -> None:
    """Sync portfolio holdings."""
    if dry_run:
        print(f"  🔍 {stream.name}: Would sync {len(portfolio.holdings)} holding(s)")
        for holding in portfolio.holdings:
            print(f"    - {holding.stock_ticker}: {holding.shares:.4f} shares")
    else:
        success = await update_account_holdings(mm, stream.account_id, portfolio)
        if success:
            print(f"  ✓ {stream.name}: Updated {len(portfolio.holdings)} holding(s)")
        else:
            print(f"  ❌ {stream.name}: Failed to sync")


async def _sync_stream(
    mm: MonarchMoney,
    stream: DataStream,
    data: TransactionLog | Portfolio,
    dry_run: bool,
) -> None:
    """Route data to appropriate sync handler based on stream type."""
    match stream.stream_type:
        case StreamType.TRANSACTIONS:
            await _sync_transactions(mm, stream, data, dry_run)
        case StreamType.PORTFOLIO:
            await _sync_portfolio(mm, stream, data, dry_run)


async def sync_integration(
    mm: MonarchMoney,
    integration: Integration,
    dry_run: bool = False,
) -> None:
    """Sync all data streams for a single integration.

    Fetches platform data once and feeds it to all configured streams.
    """
    print(f"\n🔄 {integration.name}")

    try:
        data = integration.data_fetcher()
        for stream in integration.data_streams:
            try:
                extracted_data = stream.extractor(data)
                await _sync_stream(mm, stream, extracted_data, dry_run)
            except Exception as e:
                print(f"  ❌ {stream.name}: {type(e).__name__}: {e}")

    except Exception as e:
        print(f"  ❌ Failed to fetch data: {type(e).__name__}: {e}")


async def sync_all(
    platforms: list[Platform],
    dry_run: bool = False,
) -> None:
    """Sync data from financial platforms to Monarch Money.

    Args:
        platforms: List of platforms to sync
        dry_run: If True, only show what would be synced without making changes
    """
    mm = await login()

    for platform in platforms:
        integration = INTEGRATIONS[platform]
        await sync_integration(mm, integration, dry_run)

    print(f"\n{'✓ Dry run complete' if dry_run else '✓ Sync complete'}")
