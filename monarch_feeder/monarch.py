#!/usr/bin/env python3
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pyotp
from botasaurus.browser import Driver, browser
from dotenv import load_dotenv
from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport
from graphql import DocumentNode, ExecutionResult, OperationDefinitionNode
from monarchmoney import MonarchMoney

from monarch_feeder.financial_models import (
    Holding,
    Portfolio,
    Transaction,
    TransactionLog,
)

load_dotenv(".env", override=True)

MONARCH_APP_URL = "https://app.monarch.com"
MONARCH_LOGIN_URL = f"{MONARCH_APP_URL}/login"
# monarchmoney still points at api.monarchmoney.com, which now 301s to
# api.monarch.com. aiohttp turns the redirected POST into a bodyless GET, so we
# address the current host directly.
MONARCH_GRAPHQL_URL = "https://api.monarch.com/graphql"
# Cloudflare fronts the API and blocks default client user agents, including
# the one monarchmoney ships with, so we present ourselves as the web app.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
SESSION_FILE = Path(".mm/mm_session.json")


@dataclass
class MonarchSession:
    """The credentials Monarch's web app uses to authenticate API calls.

    Monarch used to hand out an `Authorization: Token ...` value that the
    monarchmoney library could reuse. It now keeps the session in an httpOnly
    `session_id` cookie instead, so we carry the cookies (and the device UUID
    the web app registers itself with) rather than a bearer token.
    """

    session_id: str
    csrf_token: str
    device_uuid: str


def _session_headers(session: MonarchSession) -> dict[str, str]:
    """Build the headers that authenticate a request as this session.

    The API enforces Django's CSRF checks, so alongside the session cookie it
    wants the CSRF token echoed in a header and an Origin/Referer from the web
    app - without the Referer it answers "CSRF Failed: Referer checking failed".
    """
    return {
        "Cookie": f"session_id={session.session_id}; csrftoken={session.csrf_token}",
        "X-CSRFToken": session.csrf_token,
        "device-uuid": session.device_uuid,
        "Origin": MONARCH_APP_URL,
        "Referer": f"{MONARCH_APP_URL}/",
        "User-Agent": BROWSER_USER_AGENT,
    }


def _operation_name(document: DocumentNode) -> str | None:
    """Return the name of the first named operation in a GraphQL document."""
    for definition in document.definitions:
        if isinstance(definition, OperationDefinitionNode) and definition.name:
            return definition.name.value
    return None


def _serialize_payload(payload: dict[str, Any]) -> str:
    """Serialize a GraphQL payload, filling in the fields Monarch requires.

    gql omits `variables` whenever it is empty, but Monarch rejects requests
    that leave it out, so we default it here rather than at call time.
    """
    return json.dumps({"variables": {}, **payload})


class WebAppTransport(AIOHTTPTransport):
    """Transport that shapes requests the way Monarch's web app does.

    Monarch rejects any request that omits `operationName` or `variables`.
    gql only sends an operation name when one is passed explicitly, and
    monarchmoney never passes one, so we recover it from the query itself.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("json_serialize", _serialize_payload)
        super().__init__(*args, **kwargs)

    async def execute(
        self,
        document: DocumentNode,
        variable_values: dict[str, Any] | None = None,
        operation_name: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await super().execute(
            document,
            variable_values,
            operation_name or _operation_name(document),
            *args,
            **kwargs,
        )


def client_for_session(session: MonarchSession) -> MonarchMoney:
    """Create a MonarchMoney client that authenticates with a browser session."""
    mm = MonarchMoney()
    # The library authenticates with a bearer token by default; swap in the
    # cookie headers the API now expects.
    mm._headers.pop("Authorization", None)
    mm._headers.update(_session_headers(session))

    def graphql_client() -> Client:
        return Client(
            transport=WebAppTransport(
                url=MONARCH_GRAPHQL_URL,
                headers=mm._headers,
                timeout=mm.timeout,
            ),
            fetch_schema_from_transport=False,
            execute_timeout=mm.timeout,
        )

    mm._get_graphql_client = graphql_client
    return mm


def save_session(session: MonarchSession, path: Path = SESSION_FILE) -> None:
    """Persist a session so later runs can skip the browser login."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(session), indent=2))
    print(f"Saved new session to file {path}")


def load_session(path: Path = SESSION_FILE) -> MonarchSession | None:
    """Load a previously saved session, if one exists and is well-formed."""
    if not path.exists():
        return None
    try:
        return MonarchSession(**json.loads(path.read_text()))
    except (json.JSONDecodeError, TypeError) as e:
        print(f"Ignoring unreadable session file {path}: {e}")
        return None


def _submit_mfa_code(driver: Driver) -> None:
    """Enter the TOTP code if Monarch prompts for one."""
    secret = os.environ.get("MONARCH_MFA_SECRET")
    if not secret:
        return

    code_input = driver.select(
        'input[name="totp"], input[autocomplete="one-time-code"]', wait=15
    )
    if not code_input:
        print("No MFA prompt appeared, continuing...")
        return

    code = pyotp.TOTP(secret).now()
    print(f"Entering MFA code: {code}")
    code_input.type(code)
    driver.short_random_sleep()

    submit_button = driver.select('button[type="submit"]', wait=10)
    if submit_button:
        submit_button.click()
    driver.sleep(5)


def browser_login(driver: Driver) -> None:
    """Log in to Monarch through the web app's own sign-in form."""
    print("Navigating to Monarch login page...")
    driver.get(MONARCH_LOGIN_URL)
    driver.short_random_sleep()

    print("Filling in email...")
    driver.wait_for_element('input[name="username"]', wait=20)
    driver.select('input[name="username"]').type(os.environ["MONARCH_EMAIL"])
    driver.short_random_sleep()

    print("Filling in password...")
    driver.select('input[name="password"]').type(os.environ["MONARCH_PASSWORD"])
    driver.short_random_sleep()

    print("Clicking Sign in button...")
    driver.select('button[type="submit"]').click()
    driver.sleep(5)

    _submit_mfa_code(driver)


def extract_session(
    driver: Driver, max_retries: int = 10, retry_delay: int = 3
) -> MonarchSession:
    """Poll the browser until the session cookies appear after a login.

    Raises:
        ValueError: If the session cookies never show up
    """
    for attempt in range(max_retries):
        cookies = {
            cookie.get("name"): cookie.get("value")
            for cookie in driver.get_cookies()
            if cookie.get("name") in ("session_id", "csrftoken")
        }
        device_uuid = driver.run_js(
            "return localStorage.getItem('monarchDeviceUUID');"
        )

        if cookies.get("session_id") and cookies.get("csrftoken") and device_uuid:
            print(f"Found Monarch session on attempt {attempt + 1}")
            return MonarchSession(
                session_id=cookies["session_id"],
                csrf_token=cookies["csrftoken"],
                device_uuid=device_uuid,
            )

        print(
            f"Session not found yet, retrying in {retry_delay}s... "
            f"(attempt {attempt + 1}/{max_retries})"
        )
        driver.sleep(retry_delay)

    raise ValueError(
        "Could not find the Monarch session cookies. The login may not have "
        "completed - check for an MFA or CAPTCHA prompt."
    )


@browser(
    block_images=False,
    reuse_driver=False,
    output=None,
)
def get_session_via_browser(driver: Driver, data: Any = None) -> MonarchSession:
    """
    Log in to Monarch in a real browser and extract the session credentials.

    Monarch's /auth/login/ endpoint is reCAPTCHA-gated and throttles scripted
    password logins, and it no longer issues a reusable bearer token, so we log
    in the way the web app does and carry its session cookies.

    Args:
        driver: Botasaurus Driver instance (automatically injected by decorator)
        data: Optional data parameter (automatically passed by decorator, not used)

    Returns:
        The Monarch session credentials

    Raises:
        ValueError: If the session cannot be extracted after login
    """
    browser_login(driver)
    return extract_session(driver)


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

    # If we have a saved session, try to reuse it before logging in again
    session = load_session()
    if session:
        print("Loading existing session")
        mm = client_for_session(session)
        if await verify_session(mm):
            print("Existing session verified")
            return mm
        print("Existing session not verified, deleting")
        SESSION_FILE.unlink(missing_ok=True)

    # Otherwise, perform a fresh login through the browser
    print("Performing fresh login")
    session = get_session_via_browser()
    if session is None:
        raise Exception("Browser login failed to produce a Monarch session")
    mm = client_for_session(session)

    # Verify the new session and save it
    if not await verify_session(mm):
        raise Exception("Failed to verify session after fresh login")

    save_session(session)

    return mm


async def get_transactions_for_account(
    mm: MonarchMoney, account_id: str, account_name: str, num_days: int = 60
) -> TransactionLog:
    """
    Get transactions for a specific account.

    Args:
        mm: MonarchMoney instance
        account_id: The account ID to get transactions for
        account_name: The standardized account name to use for transactions

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
        return Transaction(
            date=transaction["date"],
            user_account=account_name,
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

    return TransactionLog(transactions=standardized_transactions)


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
    mm: MonarchMoney,
    transaction: Transaction,
    account_id: str,
    category_id: str,
    update_balance: bool = False,
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
        update_balance=update_balance,
    )

    return response


async def get_account_holdings(mm: MonarchMoney, account_id: str) -> Portfolio:
    """
    Get the holdings for a specific account.
    """
    holdings = []
    response = await mm.get_account_holdings(int(account_id))

    if response.get("portfolio", {}).get("aggregateHoldings", {}).get("edges"):
        for edge in response["portfolio"]["aggregateHoldings"]["edges"]:
            node = edge.get("node", {})
            ticker = node.get("security", {}).get("ticker")
            quantity = node.get("quantity", 0.0)
            holding_id = node.get("holdings", [{}])[0].get("id")

            holdings.append(
                Holding(stock_ticker=ticker, shares=quantity, holding_id=holding_id)
            )

    return Portfolio(holdings=holdings)


def _holding_error(response: Any) -> str | None:
    """Return the error from a holding mutation response, if it failed.

    create_manual_holding_by_ticker reports failures in its return value rather
    than raising, so an unchecked call can leave a holding deleted and not
    recreated while the sync still reports success.
    """
    if not isinstance(response, dict):
        return None
    if response.get("errors"):
        return str(response["errors"])
    payload = response.get("createManualHolding") or {}
    if isinstance(payload, dict) and payload.get("errors"):
        return str(payload["errors"])
    return None


async def _create_holding(
    mm: MonarchMoney, account_id: str, ticker: str, shares: float
) -> None:
    """Create a manual holding, raising if Monarch rejected it.

    Raises:
        ValueError: If Monarch returned an error instead of creating the holding
    """
    response = await mm.create_manual_holding_by_ticker(
        account_id=account_id, ticker=ticker, quantity=shares
    )
    error = _holding_error(response)
    if error:
        raise ValueError(f"Monarch rejected the {ticker} holding: {error}")


async def update_account_holdings(
    mm: MonarchMoney, account_id: str, target_holdings: Portfolio
) -> bool:
    """
    Update the holdings for a specific account using Monarch Money's manual holdings API.

    Args:
        mm: MonarchMoney instance
        account_id: The account ID to update holdings for
        target_holdings: Target portfolio with desired holdings

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Get current holdings
        current_holdings = await get_account_holdings(mm, account_id)
        current_holdings_map = current_holdings.to_dict()
        target_holdings_map = target_holdings.to_dict()

        # Update existing holdings that have changed quantities
        for ticker, target_holding_data in target_holdings_map.items():
            target_shares = target_holding_data.shares
            if ticker in current_holdings_map:
                current_holding_data = current_holdings_map[ticker]
                current_shares = current_holding_data.shares
                holding_id = current_holding_data.holding_id
                if abs(current_shares - target_shares) > 0.0001:
                    await mm.delete_manual_holding(holding_id)
                    await _create_holding(mm, account_id, ticker, target_shares)
                    print(
                        f"Updated holding {ticker} from {current_shares:.4f} -> {target_shares:.4f}"
                    )
            else:
                # Create new holding
                await _create_holding(mm, account_id, ticker, target_shares)
                print(f"Created holding {ticker} with {target_shares:.4f} shares")

        # Delete holdings not in target portfolio
        for ticker, current_holding_data in current_holdings_map.items():
            if ticker not in target_holdings_map and current_holding_data.shares > 0:
                holding_id = current_holding_data.holding_id
                await mm.delete_manual_holding(holding_id)

        return True

    except Exception as e:
        print(f"Error updating account holdings: {e}")
        return False
