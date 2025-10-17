"""
Functions for interacting with Human Interest GraphQL API.
"""

import os
from dataclasses import dataclass, field
from typing import Any

import requests
from botasaurus.browser import Driver, browser
from dotenv import load_dotenv

from monarch_feeder.financial_models import (
    Holding,
    Portfolio,
    Transaction,
    TransactionLog,
)

load_dotenv()

HUMAN_INTEREST_EMAIL = os.getenv("HUMAN_INTEREST_EMAIL")
HUMAN_INTEREST_PASSWORD = os.getenv("HUMAN_INTEREST_PASSWORD")


@dataclass
class HumanInterestSession:
    auth_sid: str = field(
        default="",
        doc="The connect.auth.sid cookie value (session authentication)",
    )
    connect_sid: str = field(
        default="", doc="The connect.sid cookie value (session identifier)"
    )
    company_id: str = field(
        default="", doc="The x-hi-company-id header value (company identifier)"
    )
    context_id: str = field(
        default="", doc="The x-hi-context-id header value (account context)"
    )


def login(driver: Driver) -> None:
    """Login to Human Interest."""

    print("Navigating to Human Interest login page...")
    driver.get("https://app.humaninterest.com/login")
    driver.short_random_sleep()

    print("Filling in email...")
    driver.wait_for_element("input#username", wait=10)
    email_input = driver.select("input#username")
    email_input.type(HUMAN_INTEREST_EMAIL)
    driver.short_random_sleep()

    print("Clicking next button...")
    next_button = driver.select("button[data-testid='btn-login-email-submit']")
    next_button.click()
    driver.short_random_sleep()

    print("Filling in password...")
    driver.wait_for_element("input[data-testid='input-login-password']", wait=10)
    password_input = driver.select("input[data-testid='input-login-password']")
    password_input.type(HUMAN_INTEREST_PASSWORD)
    driver.short_random_sleep()

    print("Clicking login button...")
    login_button = driver.select("button[data-testid='btn-login-with-password']")
    login_button.click()
    driver.short_random_sleep()

    print("Login completed successfully!")


def extract_session_context(driver: Driver) -> HumanInterestSession:
    """Extract session context from driver."""
    local_storage: dict[str, str] = driver.run_js(
        """
        const storage = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            storage[key] = localStorage.getItem(key);
        }
        return storage;
    """
    )

    auth_sid, connect_sid, company_id, context_id = None, None, None, None
    for key, value in local_storage.items():
        KEY_PREFIX = "hi_ppt_selected_division_"
        if key.startswith(KEY_PREFIX):
            context_id = key.split(KEY_PREFIX)[1]
            company_id = value
            break
    else:
        raise ValueError("Context ID and company ID not found in local storage.")

    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie.get("name") == "connect.auth.sid":
            auth_sid = cookie.get("value")
        elif cookie.get(
            "name"
        ) == "connect.sid" and "router.humaninterest.com" in cookie.get("domain", ""):
            connect_sid = cookie.get("value")

    if not auth_sid:
        raise ValueError("connect.auth.sid cookie not found.")

    if not connect_sid:
        raise ValueError(
            "connect.sid cookie with domain router.humaninterest.com not found."
        )

    return HumanInterestSession(
        auth_sid=auth_sid,
        connect_sid=connect_sid,
        company_id=company_id,
        context_id=context_id,
    )


@browser(
    block_images=False,
    reuse_driver=False,
    output=None,
)
def get_session(driver: Driver, data: dict[str, Any] = None) -> HumanInterestSession:
    """Get session from driver."""
    login(driver)
    return extract_session_context(driver)


def fetch_recent_activity(
    session: HumanInterestSession,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Send a GraphQL request to fetch recent activity from Human Interest.

    Args:
        session: The Human Interest session
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
        "x-hi-company-id": session.company_id,
        "x-hi-context-id": session.context_id,
        "x-hi-context-type": "participant",
    }

    # Build cookie string
    cookies = {
        "connect.auth.sid": session.auth_sid,
        "connect.sid": session.connect_sid,
    }

    response = requests.post(api_url, json=payload, headers=headers, cookies=cookies)
    response.raise_for_status()

    return response.json()


def fetch_all_recent_activity(
    session: HumanInterestSession,
    max_transactions: int = 30,
) -> dict[str, Any]:
    """
    Fetch all recent activity from Human Interest using pagination.

    Args:
        session: The Human Interest session
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
            session=session,
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


def parse_activity_to_transaction_log(
    response_data: dict[str, Any], account_name: str
) -> TransactionLog:
    """
    Parse Human Interest activity feed response into a TransactionLog.

    Args:
        response_data: The JSON response from the recentActivity GraphQL query
        account_name: The account name to use for transactions

    Returns:
        A TransactionLog containing all transactions from the activity feed

    Notes:
        - Each transaction is mapped as follows:
          * date: The activity item's date field
          * amount: The transaction's amount field (as float)
          * user_account: The provided account_name parameter
          * counterparty_account: The transaction source (e.g., "Employee Deferral")
        - Activity items without transactions are skipped
        - Negative amounts (like fees) are preserved as negative
    """
    transactions = []
    action_type_to_counterparty_and_key = {
        "human_interest_advisory_fee": ("Asset Fees", "employeeTotal"),
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
                            user_account=account_name,
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
                    user_account=account_name,
                    counterparty_account=counterparty,
                    amount=activity_item[key],
                )
            )

    return TransactionLog(transactions=transactions)


def fetch_portfolio(
    session: HumanInterestSession,
) -> dict[str, Any]:
    """
    Send a GraphQL request to fetch portfolio from Human Interest.

    Args:
        session: The Human Interest session

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
        "x-hi-company-id": session.company_id,
        "x-hi-context-id": session.context_id,
        "x-hi-context-type": "participant",
    }

    # Build cookie string
    cookies = {
        "connect.auth.sid": session.auth_sid,
        "connect.sid": session.connect_sid,
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


@dataclass
class HumanInterestData:
    transactions: TransactionLog
    portfolio: Portfolio


def get_human_interest_data(account_name: str) -> HumanInterestData:
    """
    Get Human Interest data for transactions and portfolio.

    Args:
        account_name: The account name to use for transactions
    """
    session = get_session()
    recent_activity = fetch_all_recent_activity(session)
    transactions = parse_activity_to_transaction_log(recent_activity, account_name)
    portfolio_response = fetch_portfolio(session)
    portfolio = parse_portfolio_response(portfolio_response)

    return HumanInterestData(transactions=transactions, portfolio=portfolio)
