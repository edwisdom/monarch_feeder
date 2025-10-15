"""
Functions for interacting with Rippling Elevate Accounts API.
"""

import os
from typing import Any

import requests
from dateutil.parser import parse as parse_datetime
from dotenv import load_dotenv

from monarch_feeder.computer_use_demo.models import (
    Holding,
    Portfolio,
    Transaction,
    TransactionLog,
)

load_dotenv()

EMPLOYER_NAME = os.getenv("EMPLOYER_NAME")


def parse_date(datetime_str: str) -> str:
    """
    Parse a date string into a YYYY-MM-DD format.
    """
    return parse_datetime(datetime_str).date().isoformat()


def fetch_enrollments(bearer_token: str) -> dict[str, Any]:
    """
    Send a GET request to fetch enrollments from Rippling Elevate Accounts.

    Args:
        bearer_token: The Bearer token for authorization (JWT)

    Returns:
        The JSON response from the API containing all enrollments

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = "https://gateway.prod.elevateaccounts.com/enrollments"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization": f"Bearer {bearer_token}",
        "DNT": "1",
        "Origin": "https://rippling.elevateaccounts.com",
        "Referer": "https://rippling.elevateaccounts.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }

    response = requests.get(api_url, headers=headers)
    response.raise_for_status()

    return response.json()


def parse_account_ids(response_data: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Return the account IDs for HSA and TRANSIT commuter benefit from enrollments data.

    Raises:
        ValueError if either account is not found.
    """
    hsa_account_id = next(
        (
            str(enr["account_id"])
            for enr in response_data
            if enr.get("account_type") == "HSA"
        ),
        None,
    )
    commuter_account_id = next(
        (
            str(enr["account_id"])
            for enr in response_data
            if enr.get("account_type") == "TRANSIT" and "election_periods" in enr
        ),
        None,
    )

    if not hsa_account_id:
        raise ValueError("HSA account not found in enrollments")
    if not commuter_account_id:
        raise ValueError("Commuter benefit (TRANSIT) account not found in enrollments")

    return hsa_account_id, commuter_account_id


def fetch_activities(
    bearer_token: str,
    account_id: str,
    page: int = 1,
    size: int = 10,
    has_active_hold: bool = False,
) -> dict[str, Any]:
    """
    Send a GET request to fetch activities from Rippling Elevate Accounts.

    Args:
        bearer_token: The Bearer token for authorization (JWT)
        account_id: The account ID to fetch activities for
        page: Page number to fetch (starts at 1)
        size: Number of items per page (default: 10)
        has_active_hold: Filter for transactions with active holds (default: False)

    Returns:
        The JSON response from the API

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = f"https://api.prod.elevateaccounts.com/api/api-aggregator/v2/activities/accounts/{account_id}"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization": f"Bearer {bearer_token}",
        "DNT": "1",
        "Origin": "https://rippling.elevateaccounts.com",
        "Referer": "https://rippling.elevateaccounts.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }

    params = {
        "page": page,
        "size": size,
        "has_active_hold": str(has_active_hold).lower(),
    }

    response = requests.get(api_url, headers=headers, params=params)
    response.raise_for_status()

    return response.json()


def fetch_all_activities(
    bearer_token: str,
    account_id: str,
    max_transactions: int = 100,
    page_size: int = 10,
    has_active_hold: bool = False,
) -> dict[str, Any]:
    """
    Fetch all activities from Rippling Elevate Accounts using pagination.

    Args:
        bearer_token: The Bearer token for authorization (JWT)
        account_id: The account ID to fetch activities for
        max_transactions: Maximum number of transactions to fetch across all pages
        page_size: Number of items per page (default: 10)
        has_active_hold: Filter for transactions with active holds (default: False)

    Returns:
        A combined JSON response with all activity items from all pages

    Raises:
        requests.HTTPError: If any request fails
    """
    all_activities = []
    page = 0
    total_fetched = 0

    while total_fetched < max_transactions:
        response = fetch_activities(
            bearer_token=bearer_token,
            account_id=account_id,
            page=page,
            size=page_size,
            has_active_hold=has_active_hold,
        )

        content = response.get("content", [])

        if not content:
            break

        all_activities.extend(content)
        total_fetched += len(content)

        if response.get("last", False):
            break

        page += 1

    return {"content": all_activities}


def parse_activities_to_hsa_transactions(
    response_data: dict[str, Any],
) -> TransactionLog:
    """
    Parse Rippling Elevate Accounts activities response into a TransactionLog.

    Args:
        response_data: The JSON response from the activities API
        account_name: Optional custom account name (defaults to "Rippling - {EMPLOYER_NAME} HSA")

    Returns:
        A TransactionLog containing all transactions from the activities

    Notes:
        - Each transaction is mapped as follows:
          * date: The status_date field (ISO format, converted to date)
          * amount: The transaction's amount field (as float)
          * user_account: The account name (e.g., "Rippling - {EMPLOYER_NAME} HSA")
          * counterparty_account: Based on transaction_type and metadata
        - Transactions with status other than "Complete" are skipped
        - Transaction types are mapped to descriptive counterparty accounts
    """
    transactions = []
    content = response_data.get("content", [])

    for activity in content:
        pending = activity.get("status") != "Complete"
        investment_transaction = activity.get("transaction_type") in [
            "BUY_INVESTMENT",
            "SELL_INVESTMENT",
            "INTEREST",
        ]

        if pending or investment_transaction:
            continue

        amount = activity.get("amount", 0)

        counterparty = activity.get("memo", "")

        transactions.append(
            Transaction(
                date=parse_date(activity.get("status_date")),
                user_account=f"Rippling - {EMPLOYER_NAME} HSA",
                counterparty_account=counterparty,
                amount=amount,
            )
        )

    return TransactionLog(transactions=transactions)


def fetch_portfolio(
    bearer_token: str,
    account_id: str,
) -> dict[str, Any]:
    """
    Send a GET request to fetch portfolio holdings from Rippling Elevate Accounts.

    Args:
        bearer_token: The Bearer token for authorization (JWT)
        account_id: The account ID to fetch holdings for

    Returns:
        The JSON response from the API

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = f"https://gateway.prod.elevateaccounts.com/investments/holdings?account_id={account_id}"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization": f"Bearer {bearer_token}",
        "DNT": "1",
        "Origin": "https://rippling.elevateaccounts.com",
        "Referer": "https://rippling.elevateaccounts.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }

    response = requests.get(api_url, headers=headers)
    response.raise_for_status()

    return response.json()


def parse_portfolio_response(response_data: dict[str, Any]) -> Portfolio:
    """
    Parse Rippling Elevate Accounts portfolio response into a Portfolio.

    Args:
        response_data: The JSON response from the holdings API

    Returns:
        A Portfolio containing all holdings from the investor's portfolio

    Notes:
        - Each holding is converted to a Holding with:
          * stock_ticker: The symbol field (e.g., "IVV", "IEFA")
          * shares: The shares field (number of shares held)
        - Holdings with zero shares are excluded
    """
    holdings = []
    investor_holdings = response_data.get("investor", {}).get("holdings", [])

    for holding_data in investor_holdings:
        symbol = holding_data.get("symbol")
        shares = holding_data.get("shares", 0)

        if shares > 0:
            holdings.append(
                Holding(
                    stock_ticker=symbol,
                    shares=shares,
                )
            )

    return Portfolio(holdings=holdings)


def parse_activities_to_commuter_benefits_transactions(
    response_data: dict[str, Any],
) -> TransactionLog:
    """
    Parse Rippling Elevate Accounts activities response into a TransactionLog.
    """
    transactions = []
    content = response_data.get("content", [])

    for activity in content:
        transactions.append(
            Transaction(
                date=parse_date(activity.get("status_date")),
                user_account=f"Rippling - {EMPLOYER_NAME} Commuter Benefits",
                counterparty_account=activity.get("memo"),
                amount=activity.get("amount"),
            )
        )

    return TransactionLog(transactions=transactions)
