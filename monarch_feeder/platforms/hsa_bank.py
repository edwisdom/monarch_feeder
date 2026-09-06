"""
Functions for interacting with the HSA Bank API.

HSA Bank's account portal is a white-labelled deployment of Bend, so the portal
at account.hsabank.com talks to api.bendhsa.com. Cash-side activity comes from
the bank service and investments come from the DriveWealth service.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

import requests
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

HSA_BANK_USERNAME = os.getenv("HSA_BANK_USERNAME")
HSA_BANK_PASSWORD = os.getenv("HSA_BANK_PASSWORD")
HSA_BANK_LOGIN_URL = os.getenv(
    "HSA_BANK_LOGIN_URL", "https://account.hsabank.com/#/auth/login?partner=15"
)
HSA_BANK_PORTAL_URL = "https://account.hsabank.com/"

# HSA Bank only offers email/text/call as second factors, so we can't generate
# codes the way we do for Rippling. Instead we keep a dedicated browser profile
# and pin the fingerprint that goes with it, so Okta's "Do not challenge me on
# this device again" keeps working across runs and the code is a one-time cost.
BROWSER_PROFILE = "hsa_bank"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
BROWSER_WINDOW_SIZE = [1920, 1080]

# Monarch represents uninvested cash inside an investment account as a holding
# of this security, which is priced at $1, so the share count is the dollar
# balance. HSA Bank keeps a cash floor (currently $1,000) before it invests
# anything, so leaving cash out would understate the account by at least that.
CASH_TICKER = "USD-USD"

API_BASE_URL = "https://api.bendhsa.com"
BANK_API_URL = f"{API_BASE_URL}/bank/v1"
INVESTMENT_API_URL = f"{API_BASE_URL}/drivewealth-investment-service/v2"

# Common headers for all HSA Bank API requests (excluding Authorization)
BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://account.hsabank.com",
    "Referer": "https://account.hsabank.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


def get_headers(access_token: str) -> dict[str, str]:
    """Return headers with authorization token.

    The portal sends the raw JWT, with no "Bearer" prefix; adding one gets a 401.
    """
    return {**BASE_HEADERS, "Authorization": access_token}


def login(driver: Driver) -> None:
    """
    Login to HSA Bank.

    HSA Bank authenticates through Okta's sign-in widget, which asks for the
    username first and only then reveals the password field.

    Args:
        driver: Botasaurus Driver instance

    Raises:
        TimeoutError: If login takes too long or elements not found
    """
    print("Navigating to HSA Bank login page...")
    driver.get(HSA_BANK_LOGIN_URL)
    driver.short_random_sleep()

    print("Filling in username...")
    driver.wait_for_element("#idp-discovery-username", wait=20)
    username_input = driver.select("#idp-discovery-username")
    username_input.type(HSA_BANK_USERNAME)
    driver.short_random_sleep()

    print("Clicking Next button...")
    driver.select("#idp-discovery-submit").click()
    driver.short_random_sleep()

    print("Filling in password...")
    driver.wait_for_element('input[type="password"]', wait=20)
    password_input = driver.select('input[type="password"]')
    password_input.type(HSA_BANK_PASSWORD)
    driver.short_random_sleep()

    print("Clicking Sign in button...")
    sign_in_button = driver.select(
        'input[type="submit"], button[type="submit"]', wait=10
    )
    sign_in_button.click()
    driver.sleep(5)

    print(f"Login submitted, currently on: {driver.current_url}")


def trust_this_device(driver: Driver) -> bool:
    """Tick Okta's "Do not challenge me on this device again" box if it's shown.

    This is what makes the persistent profile pay off: once the box is ticked
    and the factor is verified, Okta drops a long-lived device token in the
    profile and stops asking on later runs.

    Returns:
        True if a checkbox was found and ticked
    """
    return driver.run_js(
        """
        const boxes = [...document.querySelectorAll('input[type="checkbox"]')];
        for (const box of boxes) {
            const label = (box.labels && box.labels[0] && box.labels[0].textContent)
                || box.getAttribute('aria-label')
                || (box.parentElement && box.parentElement.textContent)
                || '';
            if (/do not challenge|don't challenge|remember|trust this device/i.test(label)) {
                if (!box.checked) { box.click(); }
                return true;
            }
        }
        return false;
        """
    )


def _find_access_token(local_storage: dict[str, str]) -> str | None:
    """Find the Okta access token in a dump of the portal's local storage.

    Okta's token manager keeps its tokens under "okta-token-storage" as
    {"accessToken": {"accessToken": "<jwt>", ...}, ...}. We search generically
    so a renamed storage key doesn't break the integration.
    """
    for key, value in local_storage.items():
        if not isinstance(value, str) or "token" not in key.lower():
            continue
        try:
            stored = json.loads(value)
        except json.JSONDecodeError:
            continue
        if not isinstance(stored, dict):
            continue

        access_token = stored.get("accessToken")
        # Okta nests the JWT one level deeper than the entry name suggests.
        if isinstance(access_token, dict):
            access_token = access_token.get("accessToken")
        if isinstance(access_token, str) and access_token.startswith("ey"):
            return access_token

    return None


def _read_access_token(driver: Driver) -> str | None:
    """Read the access token out of the portal's local storage, if it's there."""
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
    return _find_access_token(local_storage)


def wait_for_access_token(
    driver: Driver,
    max_retries: int,
    retry_delay: int,
    prompt_for_mfa: bool = False,
) -> str | None:
    """Poll local storage until an access token shows up.

    Args:
        driver: Botasaurus Driver instance
        max_retries: How many times to poll
        retry_delay: Seconds between polls
        prompt_for_mfa: Print a note telling you to finish the code prompt

    Returns:
        The access token, or None if it never appeared
    """
    for attempt in range(max_retries):
        access_token = _read_access_token(driver)
        if access_token:
            print(f"Found HSA Bank access token on attempt {attempt + 1}")
            return access_token

        # Okta only shows the "don't challenge me again" box on the screen where
        # you type the code, which appears a few steps after the password, so we
        # keep trying to tick it while we wait rather than once up front.
        if prompt_for_mfa and trust_this_device(driver):
            print("Ticked 'Do not challenge me on this device again'")

        if prompt_for_mfa:
            if attempt == 0:
                print(
                    "\n  >> If HSA Bank is asking for a verification code, enter it in\n"
                    "     the browser window that just opened. Once you're through,\n"
                    "     this device is remembered and later syncs won't ask again.\n"
                )
            print(
                f"Waiting for an authenticated session, retrying in {retry_delay}s... "
                f"(attempt {attempt + 1}/{max_retries})"
            )
        driver.sleep(retry_delay)

    return None


@browser(
    block_images=False,
    reuse_driver=False,
    output=None,
    profile=BROWSER_PROFILE,
    user_agent=BROWSER_USER_AGENT,
    window_size=BROWSER_WINDOW_SIZE,
)
def get_access_token(driver: Driver, data: Any = None) -> str:
    """
    Orchestrator function to get an HSA Bank access token.

    Tries the saved browser profile first, since a trusted device usually still
    has a live Okta session, and only falls back to a full login when it
    doesn't.

    Args:
        driver: Botasaurus Driver instance (automatically injected by decorator)
        data: Optional data parameter (automatically passed by decorator, not used)

    Returns:
        The access token as a string

    Raises:
        ValueError: If the token cannot be obtained
    """
    print("Checking for a saved HSA Bank session...")
    driver.get(HSA_BANK_PORTAL_URL)
    driver.sleep(5)

    access_token = wait_for_access_token(driver, max_retries=2, retry_delay=3)
    if access_token:
        print("Reused the saved HSA Bank session, no login needed")
        return access_token

    print("No saved session, logging in...")
    login(driver)
    access_token = wait_for_access_token(
        driver, max_retries=60, retry_delay=5, prompt_for_mfa=True
    )
    if access_token:
        return access_token

    raise ValueError(
        "Could not find the HSA Bank access token in local storage. "
        "The login may not have completed."
    )


def parse_date(datetime_str: str) -> str:
    """
    Parse a date string into a YYYY-MM-DD format.
    """
    return parse_datetime(datetime_str).date().isoformat()


def fetch_transactions(
    access_token: str,
    page: int = 0,
    page_size: int = 25,
    transaction_filter: str = "All",
    include_pending: bool = False,
) -> dict[str, Any]:
    """
    Send a GET request to fetch cash transactions from HSA Bank.

    Args:
        access_token: The Okta access token for authorization (JWT)
        page: Page number to fetch (starts at 0)
        page_size: Number of items per page (default: 25)
        transaction_filter: Which transactions to include (default: "All")
        include_pending: Whether to include transactions that haven't posted

    Returns:
        The JSON response from the API, with "records" plus paging metadata

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = f"{BANK_API_URL}/transactions/"

    params = {
        "page": page,
        "transactionFilter": transaction_filter,
        "includePending": str(include_pending).lower(),
        "pageSize": page_size,
    }

    response = requests.get(api_url, headers=get_headers(access_token), params=params)
    response.raise_for_status()

    return response.json()


def fetch_all_transactions(
    access_token: str,
    max_transactions: int = 30,
    page_size: int = 25,
) -> dict[str, Any]:
    """
    Fetch cash transactions from HSA Bank using pagination.

    Args:
        access_token: The Okta access token for authorization (JWT)
        max_transactions: Maximum number of transactions to fetch across all pages
        page_size: Number of items per page (default: 25)

    Returns:
        A combined JSON response with all transaction records from all pages

    Raises:
        requests.HTTPError: If any request fails
    """
    all_records = []
    page = 0
    total_fetched = 0

    while total_fetched < max_transactions:
        response = fetch_transactions(
            access_token=access_token,
            page=page,
            page_size=page_size,
        )

        records = response.get("records", [])
        if not records:
            break

        all_records.extend(records)
        total_fetched += len(records)

        # The API clamps out-of-range pages to the last one, so trust its count
        # rather than waiting for an empty page.
        if page + 1 >= response.get("numberOfPages", 1):
            break

        page += 1

    return {"records": all_records}


def parse_transactions_to_transaction_log(
    response_data: dict[str, Any], account_name: str
) -> TransactionLog:
    """
    Parse an HSA Bank transactions response into a TransactionLog.

    Args:
        response_data: The JSON response from the transactions API
        account_name: The account name to use for transactions

    Returns:
        A TransactionLog containing all transactions from the response

    Notes:
        - Each transaction is mapped as follows:
          * date: The posted_date field (ISO format, converted to date)
          * amount: The transaction's amount field (as float)
          * user_account: The provided account_name parameter
          * counterparty_account: The transaction's description
        - Transactions that haven't posted yet are skipped
        - Cash moving to or from the brokerage is skipped, since the portfolio
          stream already reflects it, as is interest
    """
    transactions = []
    records = response_data.get("records", [])

    for record in records:
        pending = record.get("status") != "complete"
        investment_transaction = record.get("source") in ("investment", "interest")

        if pending or investment_transaction:
            continue

        transactions.append(
            Transaction(
                date=parse_date(record.get("postedDate")),
                user_account=account_name,
                counterparty_account=record.get("description", ""),
                amount=record.get("amount", 0),
            )
        )

    return TransactionLog(transactions=transactions)


def fetch_investment_summaries(access_token: str) -> list[dict[str, Any]]:
    """
    Send a GET request to fetch investment account summaries from HSA Bank.

    Each summary carries the account's holdings, so this doubles as the
    portfolio endpoint.

    Args:
        access_token: The Okta access token for authorization (JWT)

    Returns:
        The JSON response from the API: one entry per DriveWealth account

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = f"{INVESTMENT_API_URL}/summary"

    response = requests.get(api_url, headers=get_headers(access_token))
    response.raise_for_status()

    return response.json()


def fetch_cash_balance(access_token: str) -> dict[str, Any]:
    """
    Send a GET request to fetch the uninvested HSA cash balance.

    This is the cash sitting on the bank side, which is most of the account
    while the investment threshold is in force.

    Args:
        access_token: The Okta access token for authorization (JWT)

    Returns:
        The JSON response from the API, with the balance and its as-of date

    Raises:
        requests.HTTPError: If the request fails
    """
    api_url = f"{BANK_API_URL}/hsa/currentbalance"

    response = requests.get(api_url, headers=get_headers(access_token))
    response.raise_for_status()

    return response.json()


def parse_portfolio(
    summaries: list[dict[str, Any]], balance_response: dict[str, Any]
) -> Portfolio:
    """
    Parse HSA Bank investment summaries and cash balance into a Portfolio.

    Args:
        summaries: The JSON response from the investment summary API
        balance_response: The JSON response from the cash balance API

    Returns:
        A Portfolio containing the invested holdings plus uninvested cash

    Notes:
        - Each investment holding is converted to a Holding with:
          * stock_ticker: The stock_symbol field (e.g., "VTI", "VXUS")
          * shares: The open_quantity field (number of shares held)
        - Shares are summed per ticker, since a ticker can appear in more than
          one investment account
        - Cash becomes a CASH_TICKER holding whose share count is the dollar
          balance: the bank-side balance plus any cash sitting uninvested in the
          brokerage accounts
        - Holdings with zero shares are excluded, so an account with no cash
          simply has no cash holding
    """
    shares_by_ticker: dict[str, float] = {}

    for summary in summaries:
        for holding_data in summary.get("holdings", []):
            symbol = holding_data.get("stockSymbol")
            shares = holding_data.get("openQuantity", 0)

            if symbol and shares > 0:
                shares_by_ticker[symbol] = shares_by_ticker.get(symbol, 0) + shares

    cash_balance = balance_response.get("balance", 0) or 0
    cash_balance += sum(summary.get("cashBalance", 0) or 0 for summary in summaries)
    if cash_balance > 0:
        shares_by_ticker[CASH_TICKER] = cash_balance

    return Portfolio(
        holdings=[
            Holding(stock_ticker=symbol, shares=shares)
            for symbol, shares in shares_by_ticker.items()
        ]
    )


@dataclass
class HSABankData:
    transactions: TransactionLog
    portfolio: Portfolio


def get_hsa_bank_data(account_name: str) -> HSABankData:
    """
    Get HSA Bank data for transactions and portfolio holdings.

    Args:
        account_name: The account name to use for transactions
    """
    access_token = get_access_token()
    if not access_token:
        raise ValueError("Could not get an HSA Bank access token")

    all_transactions = fetch_all_transactions(access_token)
    transactions = parse_transactions_to_transaction_log(all_transactions, account_name)

    summaries = fetch_investment_summaries(access_token)
    portfolio = parse_portfolio(summaries, fetch_cash_balance(access_token))

    return HSABankData(transactions=transactions, portfolio=portfolio)
