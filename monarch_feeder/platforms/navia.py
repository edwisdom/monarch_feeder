"""
Functions for interacting with the Navia Benefits participant API.

Navia's portal talks to webapi.naviabenefits.com, where Cloudflare answers
non-browser clients with a bare 404. So unlike the other integrations, we call
the API with fetch from inside the signed-in page.
"""

import base64
import json
import os
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from botasaurus.browser import Driver, browser
from dotenv import load_dotenv

from monarch_feeder.financial_models import Transaction, TransactionLog

load_dotenv()

NAVIA_USERNAME = os.getenv("NAVIA_USERNAME")
NAVIA_PASSWORD = os.getenv("NAVIA_PASSWORD")
NAVIA_LOGIN_URL = os.getenv("NAVIA_LOGIN_URL", "https://app.naviabenefits.com/#/login")
NAVIA_TRANSACTIONS_URL = os.getenv("NAVIA_TRANSACTIONS_URL")

STATEMENT_API_URL = "https://webapi.naviabenefits.com/api/ppt/stmt/accttrans"

# Navia texts or emails a code on sign-in. "Remember this device" makes the
# portal keep a token in a cookie for 30 days from when the code was entered,
# and a dedicated browser profile carries that cookie between runs.
BROWSER_PROFILE = "navia"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def parse_statement_url(url: str | None) -> dict[str, str]:
    """Turn a statement page URL into the statement API's query parameters.

    The portal routes in the fragment, e.g. "#/statement?pid=qQ9h...&bid=29",
    and pid/bid are the API's planId/benefitTypeId.
    """
    query = parse_qs(urlparse(url or "").fragment.partition("?")[2])
    if "pid" not in query or "bid" not in query:
        raise ValueError(f"NAVIA_TRANSACTIONS_URL needs a pid and bid, got {url!r}")
    return {"planId": query["pid"][0], "benefitTypeId": query["bid"][0]}


def login(driver: Driver) -> None:
    """Log in to Navia, waiting for you to enter a code if it asks for one."""
    print("Logging in to Navia...")
    driver.get(NAVIA_LOGIN_URL)
    driver.wait_for_element("#Login_Username", wait=20)
    driver.select("#Login_Username").type(NAVIA_USERNAME)
    driver.select("#Login_Password").type(NAVIA_PASSWORD)
    driver.short_random_sleep()
    driver.select("#login-btn").click()

    prompted = False
    for _ in range(60):
        driver.sleep(5)
        # The session lands in sessionStorage, login errors show in a
        # <messagebox>, and the remember box only exists on the code step.
        state = driver.run_js(
            """
            const box = document.querySelector('input[name="rememberThisDevice"]');
            if (box && !box.checked) box.click();
            const auth = JSON.parse(sessionStorage.getItem('authorizationData') || '{}');
            const errors = [...document.querySelectorAll('messagebox')];
            return {
                signedIn: Boolean(auth.token),
                askingForCode: document.body.innerText.includes('Verify Your Identity'),
                error: errors.map((el) => el.innerText.trim()).join(' ').trim(),
            };
            """
        )
        if state["signedIn"]:
            return
        if state["askingForCode"] and not prompted:
            print(
                "\n  >> Navia wants a verification code. In the browser window, pick\n"
                "     text or email and enter it. 'Remember this device' is ticked\n"
                "     for you, so later syncs won't ask for 30 days.\n"
            )
            prompted = True
        elif state["error"] and not state["askingForCode"]:
            raise ValueError(f"Navia rejected the login: {state['error']}")

    raise TimeoutError("Timed out waiting for the Navia login to complete")


def report_device_trust(driver: Driver) -> None:
    """Say when the remembered device runs out.

    Right after a code is accepted the portal fetches the token in the
    background, so we give it a few seconds to land before the browser closes.
    The cookie is named for the base64-encoded username, then URL-encoded.
    """
    name = "NV_UserCookie-" + base64.b64encode(NAVIA_USERNAME.encode()).decode()
    for _ in range(10):
        for cookie in driver.get_cookies():
            if unquote(cookie["name"]) == name:
                expires = datetime.fromtimestamp(cookie["expires"]).date()
                days_left = (expires - date.today()).days
                print(f"Navia remembers this device until {expires} ({days_left} days)")
                return
        driver.sleep(2)

    print("Warning: Navia didn't remember this device, so next sync will need a code")


def fetch_statement(driver: Driver, params: dict[str, str]) -> dict[str, Any]:
    """Fetch every line of a benefit's statement, authenticated like the portal."""
    response = driver.run_js(
        """
        const auth = JSON.parse(sessionStorage.getItem('authorizationData'));
        return fetch(args.url, {
            credentials: 'include',
            cache: 'no-store',
            headers: {
                Accept: 'application/json, text/plain, */*',
                Authorization: 'bearer ' + auth.token,
                'X-NAVIA-CSRF-TOKEN': auth.xnaviacsrfToken,
            },
        }).then(async (r) => ({status: r.status, body: await r.text()}));
        """,
        {"url": f"{STATEMENT_API_URL}?{urlencode(params)}"},
    )
    if response["status"] != 200:
        raise ValueError(
            f"Navia statement request failed ({response['status']}): "
            f"{response['body'][:200]}"
        )
    return json.loads(response["body"])


@browser(
    block_images=False,
    reuse_driver=False,
    output=None,
    profile=BROWSER_PROFILE,
    user_agent=BROWSER_USER_AGENT,
    window_size=[1920, 1080],
)
def get_statement(driver: Driver, params: dict[str, str]) -> dict[str, Any]:
    """Log in and fetch the statement, while the browser is still open."""
    login(driver)
    report_device_trust(driver)
    return fetch_statement(driver, params)


def parse_statement(statement: dict[str, Any], account_name: str) -> TransactionLog:
    """
    Parse statement lines into a TransactionLog.

    Each line fills one of two columns: amount ("Contributed", e.g. the monthly
    transit order) or claimAmount ("Claimed", e.g. a card swipe). Claims leave
    the account, are named after the merchant, and are skipped until approved.
    """
    transactions = []
    for line in statement.get("transLines") or []:
        details = {d["name"]: d["descr"] for d in line.get("details") or []}
        if line.get("claimAmount"):
            if details.get("Status") != "Approved":
                continue
            counterparty = details.get("Merchant") or line["descr"]
            amount = -line["claimAmount"]
        elif line.get("amount"):
            counterparty, amount = line["descr"], line["amount"]
        else:
            continue

        transactions.append(
            Transaction(
                date=line["postedDate"][:10],  # ISO datetime -> YYYY-MM-DD
                user_account=account_name,
                counterparty_account=counterparty,
                amount=amount,
            )
        )

    return TransactionLog(transactions=transactions)


def get_navia_transactions(account_name: str) -> TransactionLog:
    """Get transactions for the benefit NAVIA_TRANSACTIONS_URL points at."""
    # Parse first so a bad URL fails before we open a browser
    params = parse_statement_url(NAVIA_TRANSACTIONS_URL)
    statement = get_statement(params)
    if not statement:
        raise ValueError("Could not fetch the Navia statement")

    return parse_statement(statement, account_name)
