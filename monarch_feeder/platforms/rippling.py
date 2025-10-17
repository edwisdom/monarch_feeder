"""
Functions for interacting with Rippling Elevate Accounts API.
"""

import os
from typing import Any

import oathtool
import requests
from attr import dataclass
from botasaurus.browser import Driver, browser
from dateutil.parser import parse as parse_datetime
from dotenv import load_dotenv

from monarch_feeder.financial_models import (
    Holding,
    Portfolio,
    Transaction,
    TransactionLog,
)

load_dotenv()

EMPLOYER_NAME = os.getenv("EMPLOYER_NAME")
RIPPLING_EMAIL = os.getenv("RIPPLING_EMAIL")
RIPPLING_PASSWORD = os.getenv("RIPPLING_PASSWORD")
RIPPLING_MFA_SECRET = os.getenv("RIPPLING_MFA_SECRET")

# Common headers for all Rippling API requests (excluding Authorization)
BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9",
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


def get_headers(bearer_token: str) -> dict[str, str]:
    """Return headers with authorization token."""
    return {**BASE_HEADERS, "Authorization": f"Bearer {bearer_token}"}


def login(driver: Driver) -> None:
    """
    Login to Rippling (without extracting bearer token).

    This function handles the complete login flow including:
    - Email and password entry
    - Role selection (employer account)
    - MFA/OTP verification

    Args:
        driver: Botasaurus Driver instance

    Raises:
        TimeoutError: If login takes too long or elements not found
    """
    print("Navigating to Rippling login page...")
    driver.get("https://app.rippling.com/login")
    driver.short_random_sleep()

    print("Filling in email...")
    driver.wait_for_element("input#email", wait=10)
    email_input = driver.select("input#email")
    email_input.type(RIPPLING_EMAIL)
    driver.short_random_sleep()

    print("Clicking Continue button...")
    continue_btn = driver.get_element_containing_text("Continue", wait=10)
    continue_btn.click()
    driver.short_random_sleep()

    print("Filling in password...")
    driver.wait_for_element('input[type="password"]', wait=10)
    password_input = driver.select('input[type="password"]')
    password_input.type(RIPPLING_PASSWORD)
    driver.short_random_sleep()

    print("Clicking login button...")
    login_btn = None
    for button_text in ["Continue", "Sign in", "Log in"]:
        login_btn = driver.get_element_containing_text(button_text, wait=2)
        if login_btn:
            break
    login_btn.click()
    driver.short_random_sleep()

    print("Checking for role picker...")
    driver.wait_for_element("#rolePickerForm", wait=5)
    print(f"Role picker found! Selecting account containing '{EMPLOYER_NAME}'...")

    clicked = driver.run_js(
        """
        // Find all text nodes that contain the employer name
        const employerName = ARGS;
        const walker = document.createTreeWalker(
            document.getElementById('rolePickerForm'),
            NodeFilter.SHOW_TEXT,
            null
        );
        
        let node;
        while (node = walker.nextNode()) {
            if (node.textContent.includes(employerName)) {
                // Found the text node, now find the clickable parent
                let current = node.parentElement;
                while (current) {
                    if (current.hasAttribute('tabindex')) {
                        console.log('Found clickable parent for:', employerName);
                        current.click();
                        return true;
                    }
                    current = current.parentElement;
                }
            }
        }
        return false;
        """,
        EMPLOYER_NAME,
    )

    if clicked:
        print(f"Successfully clicked on account containing '{EMPLOYER_NAME}'")
        driver.short_random_sleep()
    else:
        print(f"Warning: Could not find and click element containing '{EMPLOYER_NAME}'")
        role_form = driver.select("#rolePickerForm")
        print(f"Role picker form text: {role_form.text[:200]}")

    otp = oathtool.generate_otp(RIPPLING_MFA_SECRET)
    print(f"Generated Rippling OTP: {otp}")

    driver.wait_for_element("#otpCode", wait=10)
    otp_input = driver.select("#otpCode")
    print("Entering OTP code...")
    otp_input.type(otp)
    driver.short_random_sleep()

    print("Clicking Verify button...")
    clicked = driver.run_js(
        """
        const buttons = document.querySelectorAll('button');
        for (const button of buttons) {
            if (button.textContent.trim() === 'Verify') {
                button.click();
                return true;
            }
        }
        return false;
        """
    )
    driver.short_random_sleep()

    print("Waiting for authentication to complete...")
    driver.sleep(2)  # Give the auth process time to complete
    print("Login completed successfully!")


def navigate_to_hsa(driver: Driver) -> None:
    """
    Navigate to the HSA dashboard from the Rippling app hub.

    Args:
        driver: Botasaurus Driver instance (must be logged in)

    Raises:
        PageNotFoundException: If navigation fails or timeout is reached
    """
    print("Navigating to HSA...")
    print("Clicking HSA app icon...")
    driver.wait_for_element('[data-testid="HSA"]', wait=10)
    hsa_icon = driver.select('[data-testid="HSA"]')
    hsa_icon.click()
    driver.short_random_sleep()

    print("Clicking 'Log in to your HSA account' button...")
    driver.wait_for_element('[data-testid="Log in to your HSA account"]', wait=10)
    login_button = driver.select('[data-testid="Log in to your HSA account"]')
    login_button.click()

    driver.sleep(30)
    print(f"Successfully navigated to HSA dashboard: {driver.current_url}")


def extract_bearer_token(driver: Driver) -> str:
    """
    Extract bearer token from browser storage after successful login.

    Args:
        driver: Botasaurus Driver instance (must be logged in)

    Returns:
        The bearer token as a string

    Raises:
        ValueError: If bearer token cannot be found in any storage location
    """
    print("Navigating to Rippling Elevate Accounts...")
    driver.get("https://rippling.elevateaccounts.com/")
    driver.short_random_sleep()

    print("Checking localStorage for bearer token...")
    local_storage = driver.run_js(
        """
        const storage = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            storage[key] = localStorage.getItem(key);
        }
        return storage;
    """
    )
    if "token" not in local_storage:
        raise ValueError("Bearer token not found in any storage location.")

    return local_storage["token"]


@browser(
    block_images=False,
    reuse_driver=False,
    output=None,
)
def get_bearer_token(driver: Driver, data: Any = None) -> str:
    """
    Orchestrator function to login to Rippling and extract bearer token.

    Args:
        driver: Botasaurus Driver instance (automatically injected by decorator)
        data: Optional data parameter (automatically passed by decorator, not used)

    Returns:
        The bearer token as a string

    Raises:
        ValueError: If credentials are not found or token cannot be extracted
    """
    login(driver)
    navigate_to_hsa(driver)
    return extract_bearer_token(driver)


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

    response = requests.get(api_url, headers=get_headers(bearer_token))
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

    params = {
        "page": page,
        "size": size,
        "has_active_hold": str(has_active_hold).lower(),
    }

    response = requests.get(api_url, headers=get_headers(bearer_token), params=params)
    response.raise_for_status()

    return response.json()


def fetch_all_activities(
    bearer_token: str,
    account_id: str,
    max_transactions: int = 30,
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
    response_data: dict[str, Any], account_name: str
) -> TransactionLog:
    """
    Parse Rippling Elevate Accounts activities response into a TransactionLog.

    Args:
        response_data: The JSON response from the activities API
        account_name: The account name to use for transactions

    Returns:
        A TransactionLog containing all transactions from the activities

    Notes:
        - Each transaction is mapped as follows:
          * date: The status_date field (ISO format, converted to date)
          * amount: The transaction's amount field (as float)
          * user_account: The provided account_name parameter
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
                user_account=account_name,
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

    response = requests.get(api_url, headers=get_headers(bearer_token))
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
    response_data: dict[str, Any], account_name: str
) -> TransactionLog:
    """
    Parse Rippling Elevate Accounts activities response into a TransactionLog.

    Args:
        response_data: The JSON response from the activities API
        account_name: The account name to use for transactions
    """
    transactions = []
    content = response_data.get("content", [])

    for activity in content:
        transactions.append(
            Transaction(
                date=parse_date(activity.get("status_date")),
                user_account=account_name,
                counterparty_account=activity.get("memo"),
                amount=activity.get("amount"),
            )
        )

    return TransactionLog(transactions=transactions)


@dataclass
class RipplingData:
    hsa_transactions: TransactionLog
    hsa_portfolio: Portfolio
    commuter_benefits_transactions: TransactionLog


def get_rippling_data(
    hsa_account_name: str, commuter_account_name: str
) -> RipplingData:
    """
    Get Rippling data for HSA and commuter benefits.

    Args:
        hsa_account_name: The account name to use for HSA transactions
        commuter_account_name: The account name to use for commuter benefits transactions
    """
    bearer_token = get_bearer_token()
    hsa_account_id, commuter_benefits_account_id = parse_account_ids(
        fetch_enrollments(bearer_token)
    )

    hsa_activities = fetch_all_activities(bearer_token, hsa_account_id)
    hsa_transactions = parse_activities_to_hsa_transactions(
        hsa_activities, hsa_account_name
    )

    hsa_portfolio_response = fetch_portfolio(bearer_token, hsa_account_id)
    hsa_portfolio = parse_portfolio_response(hsa_portfolio_response)

    commuter_benefits_activities = fetch_all_activities(
        bearer_token, commuter_benefits_account_id
    )
    commuter_benefits_transactions = parse_activities_to_commuter_benefits_transactions(
        commuter_benefits_activities, commuter_account_name
    )

    return RipplingData(
        hsa_transactions=hsa_transactions,
        hsa_portfolio=hsa_portfolio,
        commuter_benefits_transactions=commuter_benefits_transactions,
    )
