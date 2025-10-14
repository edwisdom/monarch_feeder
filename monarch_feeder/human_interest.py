"""
Functions for interacting with Human Interest GraphQL API.
"""

import os
from typing import Any

import requests
from dotenv import load_dotenv

from monarch_feeder.computer_use_demo.models import (
    Holding,
    Portfolio,
    Transaction,
    TransactionLog,
)

load_dotenv()

EMPLOYER_NAME = os.getenv("EMPLOYER_NAME")


def fetch_recent_activity(
    auth_sid: str,
    connect_sid: str,
    company_id: str,
    context_id: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Send a GraphQL request to fetch recent activity from Human Interest.

    Args:
        auth_sid: The connect.auth.sid cookie value (session authentication)
        connect_sid: The connect.sid cookie value (session identifier)
        company_id: The x-hi-company-id header value (company identifier)
        context_id: The x-hi-context-id header value (account context)
        limit: Number of activity items to fetch per page (default: 20, max: 20)
        offset: Number of items to skip (for pagination)

    Returns:
        The JSON response from the API

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = "https://router.humaninterest.com/router/provider/graphql"
    query = """query recentActivity($page: ActivityPagination!) {
  personActivityFeed(page: $page) {
    actionType
    employeeTotal
    employerTotal
    total
    date
    type
  }
}"""

    payload = {
        "operationName": "recentActivity",
        "variables": {"page": {"limit": limit, "offset": offset}},
        "query": query,
    }

    # Build headers with authentication and context
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Origin": "https://app.humaninterest.com",
        "Referer": "https://app.humaninterest.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "x-hi-company-id": company_id,
        "x-hi-context-id": context_id,
        "x-hi-context-type": "participant",
    }

    # Build cookie string
    cookies = {
        "connect.auth.sid": auth_sid,
        "connect.sid": connect_sid,
    }

    response = requests.post(api_url, json=payload, headers=headers, cookies=cookies)
    response.raise_for_status()

    return response.json()


def fetch_all_recent_activity(
    auth_sid: str,
    connect_sid: str,
    company_id: str,
    context_id: str,
    max_transactions: int = 100,
) -> dict[str, Any]:
    """
    Fetch all recent activity from Human Interest using pagination.

    Args:
        auth_sid: The connect.auth.sid cookie value (session authentication)
        connect_sid: The connect.sid cookie value (session identifier)
        company_id: The x-hi-company-id header value (company identifier)
        context_id: The x-hi-context-id header value (account context)
        max_transactions: Maximum number of transactions to fetch across all pages

    Returns:
        A combined JSON response with all activity items from all pages

    Raises:
        requests.HTTPError: If any request fails
    """
    all_activities = []
    page_size = 20  # API limit per page
    offset = 0

    while offset < max_transactions:
        response = fetch_recent_activity(
            auth_sid=auth_sid,
            connect_sid=connect_sid,
            company_id=company_id,
            context_id=context_id,
            limit=page_size,
            offset=offset,
        )

        activity_feed = response.get("data", {}).get("personActivityFeed", [])

        if not activity_feed:
            # No more results
            break

        all_activities.extend(activity_feed)
        offset += page_size

        # If we got fewer results than the page size, we've reached the end
        if len(activity_feed) < page_size:
            break

    return {"data": {"personActivityFeed": all_activities}}


def parse_activity_to_transaction_log(response_data: dict[str, Any]) -> TransactionLog:
    """
    Parse Human Interest activity feed response into a TransactionLog.

    Args:
        response_data: The JSON response from the recentActivity GraphQL query

    Returns:
        A TransactionLog containing all transactions from the activity feed

    Notes:
        - Each transaction is mapped as follows:
          * date: The activity item's date field
          * amount: The transaction's amount field (as float)
          * user_account: The fund symbol (e.g., "VTIAX")
          * counterparty_account: The transaction source (e.g., "Employee Deferral")
        - Activity items without transactions are skipped
        - Negative amounts (like fees) are preserved as negative
    """
    transactions = []
    action_type_to_counterparty_and_key = {
        "human_interest_advisory_fee": ("Advisory Fee", "employeeTotal"),
        "dividend": ("Dividend", "total"),
        "rollover": ("Rollover", "total"),
    }

    activity_feed = response_data.get("data", {}).get("personActivityFeed", [])

    for activity_item in activity_feed:
        is_pending = activity_item.get("type") == "contributionPending"
        is_rebalance = activity_item.get("actionType") == "rebalance"
        all_zeroes = (
            activity_item.get("employeeTotal") == 0
            and activity_item.get("employerTotal") == 0
            and activity_item.get("total") == 0
        )

        if is_pending or is_rebalance or all_zeroes:
            continue

        if activity_item.get("actionType") == "contribution":
            for key, label in [
                ("employeeTotal", "Employee Contribution"),
                ("employerTotal", "Employer Contribution"),
            ]:
                if activity_item[key] != 0:
                    transactions.append(
                        Transaction(
                            date=activity_item["date"],
                            user_account=f"Human Interest - {EMPLOYER_NAME} 401k",
                            counterparty_account=label,
                            amount=activity_item[key],
                        )
                    )
        else:
            counterparty, key = action_type_to_counterparty_and_key.get(
                activity_item["actionType"], (activity_item["actionType"], "total")
            )
            transactions.append(
                Transaction(
                    date=activity_item["date"],
                    user_account=f"Human Interest - {EMPLOYER_NAME} 401k",
                    counterparty_account=counterparty,
                    amount=activity_item[key],
                )
            )

    return TransactionLog(transactions=transactions)


def fetch_portfolio(
    auth_sid: str,
    connect_sid: str,
    company_id: str,
    context_id: str,
) -> dict[str, Any]:
    """
    Send a GraphQL request to fetch portfolio from Human Interest.

    Args:
        auth_sid: The connect.auth.sid cookie value (session authentication)
        connect_sid: The connect.sid cookie value (session identifier)
        company_id: The x-hi-company-id header value (company identifier)
        context_id: The x-hi-context-id header value (account context)

    Returns:
        The JSON response from the API

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = "https://router.humaninterest.com/router/provider/graphql"
    query = """query currentPerson {
  currentPerson {
    id
    portfolioAllocations {
      symbol
      sharesEmployerContribution
      sharesLoan
      sharesProfitSharing
      sharesRollover
      sharesRolloverRoth
      sharesRoth
      sharesSafeHarborMatch
      sharesSafeHarborNonelectiveMatch
      sharesTraditional
    }
  }
}"""

    payload = {
        "operationName": "currentPerson",
        "variables": {},
        "query": query,
    }

    # Build headers with authentication and context
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Origin": "https://app.humaninterest.com",
        "Referer": "https://app.humaninterest.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "x-hi-company-id": company_id,
        "x-hi-context-id": context_id,
        "x-hi-context-type": "participant",
    }

    # Build cookie string
    cookies = {
        "connect.auth.sid": auth_sid,
        "connect.sid": connect_sid,
    }

    response = requests.post(api_url, json=payload, headers=headers, cookies=cookies)
    response.raise_for_status()

    return response.json()


def parse_portfolio_response(response_data: dict[str, Any]) -> Portfolio:
    """
    Parse Human Interest portfolio response into a Portfolio.

    Args:
        response_data: The JSON response from the currentPerson GraphQL query

    Returns:
        A Portfolio containing all holdings from the portfolio allocations

    Notes:
        - Each portfolio allocation is converted to a Holding with:
          * stock_ticker: The symbol field
          * shares: Sum of all shares-prefixed fields (sharesEmployerContribution,
            sharesLoan, sharesProfitSharing, sharesRollover, sharesRolloverRoth,
            sharesRoth, sharesSafeHarborMatch, sharesSafeHarborNonelectiveMatch,
            sharesTraditional)
        - Holdings with zero shares are excluded
    """
    holdings = []
    portfolio_allocations = (
        response_data.get("data", {})
        .get("currentPerson", {})
        .get("portfolioAllocations", [])
    )

    shares_fields = [
        "sharesEmployerContribution",
        "sharesLoan",
        "sharesProfitSharing",
        "sharesRollover",
        "sharesRolloverRoth",
        "sharesRoth",
        "sharesSafeHarborMatch",
        "sharesSafeHarborNonelectiveMatch",
        "sharesTraditional",
    ]

    for allocation in portfolio_allocations:
        symbol = allocation.get("symbol")
        total_shares = sum(float(allocation.get(field, 0)) for field in shares_fields)

        if total_shares > 0:
            holdings.append(
                Holding(
                    stock_ticker=symbol,
                    shares=total_shares,
                )
            )

    return Portfolio(holdings=holdings)
