#!/usr/bin/env python3
import asyncio
import os
from datetime import datetime, timedelta
from typing import Any

import pyotp
from dotenv import load_dotenv
from monarchmoney import MonarchMoney

from monarch_feeder.computer_use_demo.models import Holding, Portfolio, Transaction

load_dotenv(".env", override=True)


async def verify_session(mm: MonarchMoney) -> bool:
    try:
        subscription = await mm.get_subscription_details()
        print("Successfully verified session after login!")
        print(f"Subscription status: {subscription.get('status', 'unknown')}")
        return True
    except Exception as e:
        print(f"Failed to verify session: {type(e).__name__}: {e}")
        return False


async def login() -> MonarchMoney:

    mm = MonarchMoney()

    # If the session file exists, try to load it and verify the session
    if os.path.exists(mm._session_file):
        print("Loading existing session")
        mm.load_session()
        if await verify_session(mm):
            print("Existing session verified")
            return mm
        else:
            print("Existing session not verified, deleting")
            mm.delete_session()

    # Otherwise, perform a fresh login
    print("Performing fresh login")
    email = os.environ.get("MONARCH_EMAIL")
    password = os.environ.get("MONARCH_PASSWORD")
    secret = os.environ.get("MONARCH_MFA_SECRET")
    totp_uri = (
        f"otpauth://totp/Monarch%20Money:{email}?secret={secret}&issuer=Monarch%20Money"
    )
    code = pyotp.parse_uri(totp_uri).now()
    print(f"Using code: {code}")
    await mm.multi_factor_authenticate(
        email=email,
        password=password,
        code=code,
    )

    # Verify the new session and save it
    if not await verify_session(mm):
        raise Exception("Failed to verify session after fresh login")

    mm.save_session()
    print(f"Saved new session to file {mm._session_file}")

    return mm


async def get_transactions_for_account(
    mm: MonarchMoney, account_id: str, num_days: int = 60
) -> list[Transaction]:
    """
    Get transactions for a specific account.

    Args:
        mm: MonarchMoney instance
        account_id: The account ID to get transactions for

    Returns:
        List of transaction dictionaries
    """

    def standardize_monarch_transaction(transaction: dict[str, Any]) -> Transaction:
        """
        Convert a raw Monarch Money transaction to a standardized Transaction model.

        Args:
            transaction: Raw transaction data from Monarch Money API

        Returns:
            Transaction: Standardized transaction model
        """
        # Extract basic transaction data
        date = transaction["date"]
        amount = transaction["amount"]
        merchant_name = transaction.get("merchant", {}).get("name", "Unknown")
        monarch_account_name = transaction.get("account", {}).get(
            "displayName", "Unknown Account"
        )
        from_account, to_account = (
            (
                merchant_name,
                monarch_account_name,
            )
            if transaction["amount"] > 0
            else (monarch_account_name, merchant_name)
        )

        return Transaction(
            date=date,
            from_account=from_account,
            to_account=to_account,
            description=f"{merchant_name} - {monarch_account_name}",
            amount=abs(amount),
        )

    # Get the transactions for the last num_days days
    end_date = datetime.today()
    start_date = end_date - timedelta(days=num_days)

    # Format dates as strings
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    response = await mm.get_transactions(
        account_ids=[account_id], start_date=start_date_str, end_date=end_date_str
    )

    # Convert raw transactions to standardized Transaction models
    raw_transactions = response["allTransactions"]["results"]
    standardized_transactions = [
        standardize_monarch_transaction(tx) for tx in raw_transactions
    ]

    return standardized_transactions


async def get_portfolio_for_account(mm: MonarchMoney, account_id: str) -> Portfolio:
    """
    Get portfolio holdings for a specific account.

    Args:
        mm: MonarchMoney instance
        account_id: The account ID to get portfolio for

    Returns:
        Portfolio: Portfolio containing holdings
    """

    def standardize_monarch_holding(holding_data: dict[str, Any]) -> Holding:
        """
        Convert raw Monarch Money holding data to standardized Holding model.

        Args:
            holding_data: Raw holding data from Monarch Money API

        Returns:
            Holding: Standardized holding model
        """
        # Extract ticker from security data
        ticker = holding_data.get("security", {}).get("ticker")
        if not ticker:
            raise ValueError("No ticker found in holding data")

        shares = holding_data.get("quantity", 0.0)

        return Holding(stock_ticker=ticker, shares=shares)

    # Get portfolio holdings from Monarch Money API
    response = await mm.get_account_holdings(int(account_id))

    # Extract holdings from the response structure
    holdings_data = []
    if "portfolio" in response and "aggregateHoldings" in response["portfolio"]:
        edges = response["portfolio"]["aggregateHoldings"].get("edges", [])
        holdings_data = [edge["node"] for edge in edges if "node" in edge]

    # Convert raw holdings to standardized Holding objects
    holdings = [
        standardize_monarch_holding(holding)
        for holding in holdings_data
        if holding.get("quantity", 0) > 0  # Only include holdings with positive shares
    ]

    return Portfolio(holdings=holdings)


async def main():
    mm = await login()
    portfolio = await get_portfolio_for_account(
        mm, os.getenv("MONARCH_HUMAN_INTEREST_ACCOUNT_ID")
    )
    print(portfolio)


if __name__ == "__main__":
    asyncio.run(main())
