"""
Functions for interacting with the Navia Benefits participant API.

Navia's participant portal (app.naviabenefits.com) is an Angular app that talks
to webapi.naviabenefits.com. Cloudflare fronts both and answers non-browser
clients with a bare 404, so unlike the other integrations we can't replay the
API calls with requests. Instead we make them with fetch from inside the
signed-in page, the same way the portal does.
"""

import base64
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from botasaurus.browser import Driver, browser
from dateutil.parser import parse as parse_datetime
from dotenv import load_dotenv

from monarch_feeder.financial_models import Transaction, TransactionLog

load_dotenv()

NAVIA_USERNAME = os.getenv("NAVIA_USERNAME")
NAVIA_PASSWORD = os.getenv("NAVIA_PASSWORD")
NAVIA_LOGIN_URL = os.getenv("NAVIA_LOGIN_URL", "https://app.naviabenefits.com/#/login")
NAVIA_TRANSACTIONS_URL = os.getenv("NAVIA_TRANSACTIONS_URL")

API_BASE_URL = "https://webapi.naviabenefits.com/api"

# Navia texts or emails a code on sign-in, so there's no TOTP secret to generate
# codes from. Ticking "Remember this device" makes the portal save a device
# token in a cookie and send it with later logins to skip the code, for 30 days
# from when the code was entered. We keep a dedicated browser profile so that
# cookie survives between runs, and pin the fingerprint that goes with it.
BROWSER_PROFILE = "navia"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
BROWSER_WINDOW_SIZE = [1920, 1080]
DEVICE_COOKIE_PREFIX = "NV_UserCookie-"


def parse_statement_url(statement_url: str) -> tuple[str, str]:
    """
    Pull the plan and benefit type IDs out of a statement page URL.

    The portal routes in the URL fragment, so the query string we want is
    inside it, e.g. "#/statement?pid=qQ9h...%3D%3D&bid=29". The statement API
    takes the same two values as planId and benefitTypeId.

    Args:
        statement_url: The URL of the benefit's statement page

    Returns:
        (plan_id, benefit_type_id), with plan_id URL-decoded

    Raises:
        ValueError: If the URL doesn't carry both IDs
    """
    fragment = urlparse(statement_url or "").fragment
    query = parse_qs(fragment.partition("?")[2])
    plan_id = query.get("pid", [None])[0]
    benefit_type_id = query.get("bid", [None])[0]
    if not plan_id or not benefit_type_id:
        raise ValueError(
            "Expected pid and bid in the Navia statement URL "
            f"(NAVIA_TRANSACTIONS_URL), got {statement_url!r}"
        )
    return plan_id, benefit_type_id


def login(driver: Driver) -> None:
    """
    Submit the Navia login form.

    If this browser profile has a remembered device, the portal sends its
    token along with the password and signs straight in. Otherwise it asks for
    a code, which wait_for_login handles.

    Args:
        driver: Botasaurus Driver instance
    """
    print("Navigating to Navia login page...")
    driver.get(NAVIA_LOGIN_URL)
    driver.short_random_sleep()

    print("Filling in username...")
    driver.wait_for_element("#Login_Username", wait=20)
    driver.select("#Login_Username").type(NAVIA_USERNAME)
    driver.short_random_sleep()

    print("Filling in password...")
    driver.select("#Login_Password").type(NAVIA_PASSWORD)
    driver.short_random_sleep()

    print("Clicking login button...")
    driver.select("#login-btn").click()
    driver.sleep(3)


def _login_state(driver: Driver) -> dict[str, Any]:
    """Report whether the portal is signed in, asking for a code, or erroring.

    The portal keeps its session in sessionStorage under "authorizationData"
    once the login succeeds, and shows login failures in a <messagebox>.
    """
    return driver.run_js(
        """
        const auth = JSON.parse(sessionStorage.getItem('authorizationData') || '{}');
        const isShown = (el) => el.getClientRects().length > 0;
        const errors = [...document.querySelectorAll('messagebox')]
            .filter(isShown)
            .map((el) => el.innerText.trim())
            .filter(Boolean);
        return {
            signedIn: Boolean(auth.token),
            askingForCode: document.body.innerText.includes('Verify Your Identity'),
            error: errors.join(' '),
        };
        """
    )


def remember_this_device(driver: Driver) -> bool:
    """Tick the portal's "Remember this device" box if it's showing.

    Returns:
        True if the box was just ticked
    """
    return driver.run_js(
        """
        const box = document.querySelector(
            'input[type="checkbox"][name="rememberThisDevice"]'
        );
        if (!box || box.checked) {
            return false;
        }
        box.click();
        return true;
        """
    )


def wait_for_login(driver: Driver, max_retries: int = 60, retry_delay: int = 5) -> bool:
    """
    Poll until the portal is signed in, prompting for a code if it asks for one.

    Args:
        driver: Botasaurus Driver instance
        max_retries: How many times to poll
        retry_delay: Seconds between polls

    Returns:
        True if the portal asked for a code on the way in

    Raises:
        ValueError: If the portal rejected the login
        TimeoutError: If the portal never finished signing in
    """
    asked_for_code = False
    for attempt in range(max_retries):
        state = _login_state(driver)
        if state["signedIn"]:
            print(f"Signed in to Navia on attempt {attempt + 1}")
            return asked_for_code

        if state["askingForCode"]:
            if not asked_for_code:
                print(
                    "\n  >> Navia is asking for a verification code. In the browser\n"
                    "     window that just opened, choose text or email, then enter\n"
                    "     the code. 'Remember this device' gets ticked for you, so\n"
                    "     later syncs won't ask again.\n"
                )
                asked_for_code = True
            # The box is only on the code-entry step, which comes after you
            # pick a delivery method, so we keep trying while we wait.
            if remember_this_device(driver):
                print("Ticked 'Remember this device'")
        elif state["error"]:
            raise ValueError(f"Navia rejected the login: {state['error']}")

        print(
            f"Waiting for Navia to sign in, retrying in {retry_delay}s... "
            f"(attempt {attempt + 1}/{max_retries})"
        )
        driver.sleep(retry_delay)

    raise TimeoutError("Timed out waiting for the Navia login to complete.")


def _device_cookie(driver: Driver) -> dict[str, Any] | None:
    """Return this user's remembered-device cookie, if the profile has one.

    The portal base64-encodes the username before it builds the cookie name,
    and the cookie library then URL-encodes the name, so the cookie for
    "jdoe" is "NV_UserCookie-amRvZQ%3D%3D".
    """
    encoded_username = base64.b64encode(NAVIA_USERNAME.encode()).decode()
    name = f"{DEVICE_COOKIE_PREFIX}{encoded_username}"
    return next(
        (c for c in driver.get_cookies() if unquote(c.get("name", "")) == name),
        None,
    )


def check_device_trust(driver: Driver, just_verified: bool) -> None:
    """Report how long Navia will keep skipping the code on this device.

    The portal only fetches the device token once the code has been accepted,
    so if we just verified one we give it a few seconds to land.

    Args:
        driver: Botasaurus Driver instance (must be signed in)
        just_verified: Whether a code was entered during this login
    """
    cookie = _device_cookie(driver)
    retries = 10 if just_verified else 0
    while not cookie and retries:
        driver.sleep(2)
        cookie = _device_cookie(driver)
        retries -= 1

    if not cookie:
        print(
            "Warning: Navia hasn't remembered this device, so the next sync "
            "will ask for a code again."
        )
        return

    # Logging in with the token doesn't extend it, so this is a hard deadline
    expires = datetime.fromtimestamp(cookie["expires"])
    days_left = (expires.date() - date.today()).days
    print(
        f"Navia will skip the code on this device until {expires:%Y-%m-%d} "
        f"({days_left} days from now)"
    )


def api_get(driver: Driver, path: str, params: dict[str, Any] | None = None) -> Any:
    """
    GET a Navia API endpoint from inside the signed-in page.

    This mirrors the portal's own requests: its session cookies, plus the
    bearer token and CSRF token it keeps in sessionStorage.

    Args:
        driver: Botasaurus Driver instance (must be signed in)
        path: The endpoint path under /api, e.g. "ppt/stmt/accttrans"
        params: Optional query parameters

    Returns:
        The parsed JSON response

    Raises:
        ValueError: If the request fails
    """
    url = f"{API_BASE_URL}/{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    response = driver.run_js(
        """
        const auth = JSON.parse(sessionStorage.getItem('authorizationData') || '{}');
        return fetch(args.url, {
            credentials: 'include',
            cache: 'no-store',
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Authorization': 'bearer ' + auth.token,
                'X-NAVIA-CSRF-TOKEN': auth.xnaviacsrfToken,
            },
        }).then(async (response) => ({
            status: response.status,
            body: await response.text(),
        }));
        """,
        {"url": url},
    )
    if response["status"] != 200:
        raise ValueError(
            f"Navia API returned {response['status']} for {path}: "
            f"{response['body'][:200]}"
        )
    return json.loads(response["body"])


def fetch_statement_transactions(
    driver: Driver, plan_id: str, benefit_type_id: str
) -> dict[str, Any]:
    """
    Fetch a benefit's statement lines from Navia.

    The endpoint takes no date range: it returns every line since the
    benefit's eligibility date, and the portal filters by date client-side.

    Args:
        driver: Botasaurus Driver instance (must be signed in)
        plan_id: The plan ID (the statement URL's pid)
        benefit_type_id: The benefit type ID (the statement URL's bid)

    Returns:
        The JSON response from the API, with the lines under "transLines"

    Raises:
        ValueError: If the request fails
    """
    return api_get(
        driver,
        "ppt/stmt/accttrans",
        {"planId": plan_id, "benefitTypeId": benefit_type_id},
    )


@browser(
    block_images=False,
    reuse_driver=False,
    output=None,
    profile=BROWSER_PROFILE,
    user_agent=BROWSER_USER_AGENT,
    window_size=BROWSER_WINDOW_SIZE,
)
def get_statement(driver: Driver, data: dict[str, str]) -> dict[str, Any]:
    """
    Orchestrator function to sign in to Navia and fetch a benefit statement.

    The API call has to happen here, while the browser is still open, since
    Cloudflare turns away requests made from outside it.

    Args:
        driver: Botasaurus Driver instance (automatically injected by decorator)
        data: {"plan_id": ..., "benefit_type_id": ...} for the benefit to fetch

    Returns:
        The statement transactions response
    """
    login(driver)
    just_verified = wait_for_login(driver)
    check_device_trust(driver, just_verified)

    return fetch_statement_transactions(
        driver, data["plan_id"], data["benefit_type_id"]
    )


def parse_date(datetime_str: str) -> str:
    """
    Parse a date string into a YYYY-MM-DD format.
    """
    return parse_datetime(datetime_str).date().isoformat()


def _line_details(line: dict[str, Any]) -> dict[str, str]:
    """Flatten a statement line's details into {name: descr}."""
    return {
        detail.get("name"): detail.get("descr") for detail in line.get("details") or []
    }


def parse_statement_to_transaction_log(
    response_data: dict[str, Any], account_name: str
) -> TransactionLog:
    """
    Parse a Navia statement response into a TransactionLog.

    Args:
        response_data: The JSON response from the statement transactions API
        account_name: The account name to use for transactions

    Returns:
        A TransactionLog containing the benefit's contributions and spending

    Notes:
        - The statement has two amount columns, and each line fills one:
          * claimAmount ("Claimed"): money going out, e.g. a debit card swipe.
            These become negative transactions named after the merchant.
          * amount ("Contributed"): money going in, e.g. the monthly transit
            order. These become positive transactions named after the line,
            e.g. "Order Placed - October".
        - Claims that haven't been approved are skipped
        - Dates are the posted date, which for a card swipe is usually the
          day after the swipe itself
    """
    transactions = []

    for line in response_data.get("transLines") or []:
        details = _line_details(line)
        claimed = line.get("claimAmount")
        contributed = line.get("amount")

        if claimed:
            if details.get("Status") != "Approved":
                continue
            counterparty = details.get("Merchant") or line.get("descr", "")
            amount = -claimed
        elif contributed:
            counterparty = line.get("descr", "")
            amount = contributed
        else:
            continue

        transactions.append(
            Transaction(
                date=parse_date(line.get("postedDate")),
                user_account=account_name,
                counterparty_account=counterparty,
                amount=amount,
            )
        )

    return TransactionLog(transactions=transactions)


@dataclass
class NaviaData:
    transactions: TransactionLog


def get_navia_data(account_name: str) -> NaviaData:
    """
    Get Navia data for the benefit whose statement NAVIA_TRANSACTIONS_URL
    points at.

    Args:
        account_name: The account name to use for transactions
    """
    # Parse up front so a bad URL fails before we open a browser
    plan_id, benefit_type_id = parse_statement_url(NAVIA_TRANSACTIONS_URL)
    statement = get_statement({"plan_id": plan_id, "benefit_type_id": benefit_type_id})
    if not statement:
        raise ValueError("Could not fetch the Navia statement")

    transactions = parse_statement_to_transaction_log(statement, account_name)
    return NaviaData(transactions=transactions)
