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
        counterparty_account = transaction.get("merchant", {}).get("name", "Unknown")
        user_account = transaction.get("account", {}).get(
            "displayName", "Unknown Account"
        )
        return Transaction(
            date=transaction["date"],
            user_account=user_account,
            counterparty_account=counterparty_account,
            amount=transaction["amount"],
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


async def add_transaction_to_account(
    mm: MonarchMoney, transaction: Transaction, account_id: str, category_id: str
) -> bool:
    """
    Add a transaction to an account.

    Args:
        mm: MonarchMoney instance
        account_id: The account ID to add the transaction to
        transaction: Transaction to add
        category_id: The category ID for the transaction (required by Monarch)

    Returns:
        API response from creating the transaction
    """
    # Create the transaction using Monarch API
    response = await mm.create_transaction(
        date=transaction.date,
        account_id=account_id,
        amount=transaction.amount,
        merchant_name=transaction.counterparty_account,
        category_id=category_id,
    )

    return response


async def update_account_holdings(
    mm: MonarchMoney, account_id: str, holdings: Portfolio
) -> bool:
    """
    Update the holdings for a specific account using Monarch Money's manual holdings API.

    Args:
        mm: MonarchMoney instance
        account_id: The account ID to update holdings for
        holdings: Target portfolio with desired holdings

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Get current holdings to understand what needs to be changed
        current_response = await mm.get_account_holdings(int(account_id))
        current_holdings_data = []

        # Extract current holdings from the response
        if (
            "portfolio" in current_response
            and "aggregateHoldings" in current_response["portfolio"]
        ):
            edges = current_response["portfolio"]["aggregateHoldings"].get("edges", [])
            current_holdings_data = [edge["node"] for edge in edges if "node" in edge]

        # Create mappings for current holdings
        current_holdings_by_ticker = {}
        for holding_data in current_holdings_data:
            ticker = holding_data.get("security", {}).get("ticker")
            if ticker:
                # Get the actual holding ID from the holdings array, not the aggregate ID
                holdings_list = holding_data.get("holdings", [])
                holding_id = None
                if holdings_list:
                    holding_id = holdings_list[0].get(
                        "id"
                    )  # Get the first (should be only) holding ID

                quantity = holding_data.get("quantity", 0.0)

                current_holdings_by_ticker[ticker] = {
                    "id": holding_id,
                    "quantity": quantity,
                    "ticker": ticker,
                }

        # Track operations
        operations_succeeded = 0
        total_operations = 0

        # Process target holdings
        target_tickers = set()
        for target_holding in holdings.holdings:
            ticker = target_holding.stock_ticker
            target_quantity = target_holding.shares
            target_tickers.add(ticker)

            total_operations += 1

            if ticker in current_holdings_by_ticker:
                # For existing holdings, delete and recreate if quantity changed
                current_quantity = current_holdings_by_ticker[ticker]["quantity"]
                if abs(current_quantity - target_quantity) > 0.001:
                    try:
                        holding_id = current_holdings_by_ticker[ticker]["id"]

                        # Delete the existing holding
                        delete_success = await mm.delete_manual_holding(holding_id)

                        if delete_success:
                            # Create new holding with updated quantity
                            response = await mm.create_manual_holding_by_ticker(
                                account_id=account_id,
                                ticker=ticker,
                                quantity=target_quantity,
                            )

                            # Check for errors in the response
                            if response.get("errors"):
                                print(
                                    f"Failed to recreate holding for {ticker}: {response['errors']}"
                                )
                            elif response.get("createManualHolding", {}).get("errors"):
                                print(
                                    f"Failed to recreate holding for {ticker}: {response['createManualHolding']['errors']}"
                                )
                            elif response.get("createManualHolding", {}).get("holding"):
                                print(
                                    f"Updated {ticker}: {current_quantity} -> {target_quantity} shares (via delete+create)"
                                )
                                operations_succeeded += 1
                            else:
                                print(
                                    f"Unexpected response recreating holding for {ticker}: {response}"
                                )
                        else:
                            print(f"Failed to delete existing holding for {ticker}")
                    except Exception as e:
                        print(f"Exception updating {ticker}: {e}")
                else:
                    # No change needed
                    print(f"No change needed for {ticker}: {current_quantity} shares")
                    operations_succeeded += 1
            else:
                # Create new holding
                try:
                    response = await mm.create_manual_holding_by_ticker(
                        account_id=account_id,
                        ticker=ticker,
                        quantity=target_quantity,
                    )

                    # Check for errors in the response
                    if response.get("errors"):
                        print(
                            f"Failed to create holding for {ticker}: {response['errors']}"
                        )
                    elif response.get("createManualHolding", {}).get("errors"):
                        print(
                            f"Failed to create holding for {ticker}: {response['createManualHolding']['errors']}"
                        )
                    elif response.get("createManualHolding", {}).get("holding"):
                        print(f"Created holding for {ticker}: {target_quantity} shares")
                        operations_succeeded += 1
                    else:
                        print(
                            f"Unexpected response creating holding for {ticker}: {response}"
                        )
                except Exception as e:
                    print(f"Exception creating holding for {ticker}: {e}")

        # Remove holdings that are not in target portfolio
        for ticker, current_holding in current_holdings_by_ticker.items():
            if ticker not in target_tickers and current_holding["quantity"] > 0:
                total_operations += 1
                try:
                    holding_id = current_holding["id"]
                    success = await mm.delete_manual_holding(holding_id)

                    if success:
                        print(f"Deleted holding for {ticker}")
                        operations_succeeded += 1
                    else:
                        print(f"Failed to delete holding for {ticker}")
                except Exception as e:
                    print(f"Exception deleting holding for {ticker}: {e}")

        success = operations_succeeded == total_operations
        print(
            f"Holdings update completed: {operations_succeeded}/{total_operations} operations succeeded"
        )
        return success

    except Exception as e:
        print(f"Error updating account holdings: {e}")
        return False


async def main():
    mm = await login()
    portfolio = Portfolio(
        holdings=[
            Holding(stock_ticker="AAPL", shares=0.2),
            Holding(stock_ticker="GOOGL", shares=0.15),
        ]
    )
    account_id = os.getenv("MONARCH_HUMAN_INTEREST_ACCOUNT_ID")
    success = await update_account_holdings(mm, account_id, portfolio)


if __name__ == "__main__":
    asyncio.run(main())
