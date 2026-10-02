"""
Functions for interacting with the Empower Retirement participant API.

Plaid already syncs the 401(k)'s holdings, trades, fees and dividends, but it
files each paycheck's contribution as per-fund "Buy" rows, so the money never
shows up as income. This integration adds just the contributions, the way
Empower lists them: an "Employee Contribution" and an "Employer Contribution"
per paycheck.

The portal sits behind Cloudflare, so like Navia we call its API with fetch
from inside the signed-in page.
"""

import json
import os
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

from botasaurus.browser import Driver, browser
from dotenv import load_dotenv

from monarch_feeder.financial_models import Transaction, TransactionLog

load_dotenv()

EMPOWER_RETIREMENT_USERNAME = os.getenv("EMPOWER_RETIREMENT_USERNAME")
EMPOWER_RETIREMENT_PASSWORD = os.getenv("EMPOWER_RETIREMENT_PASSWORD")
EMPOWER_RETIREMENT_LOGIN_URL = os.getenv(
    "EMPOWER_RETIREMENT_LOGIN_URL",
    "https://participant.empower-retirement.com/participant/#/login",
)
EMPOWER_RETIREMENT_TRANSACTIONS_URL = os.getenv("EMPOWER_RETIREMENT_TRANSACTIONS_URL")

API_URL = "https://participant.empower-retirement.com/participant-web-services/rest"

# Empower only sometimes texts a code on sign-in. Ticking "Remember device" on
# the code screen has it trust the browser, and a dedicated profile carries
# that between runs.
BROWSER_PROFILE = "empower_retirement"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# How much history to read: a margin past the 60 days of Monarch transactions
# the sync compares against.
HISTORY_DAYS = 90

# The history's category codes for contributions; the rest are fees (F),
# dividends (D), transfers (TI/TO), withdrawals (W) and earnings (E).
CONTRIBUTION_CATEGORIES = ("B", "C")


def parse_account_url(url: str | None) -> dict[str, str]:
    """Turn an account page URL into the API's plan and participant IDs.

    The portal routes in the fragment, e.g.
    "#/account/15083798/290154-01/transaction-history", where the first ID is
    the participant (indId) and the second the plan account (gaId).
    """
    match = re.match(r"/account/([^/]+)/([^/]+)", urlparse(url or "").fragment)
    if not match:
        raise ValueError(
            "EMPOWER_RETIREMENT_TRANSACTIONS_URL needs a fragment like "
            f"#/account/<participant>/<plan>/..., got {url!r}"
        )
    return {"gaId": match.group(2), "indId": match.group(1)}


def login(driver: Driver) -> None:
    """Log in to Empower, waiting for you to enter a code if it asks for one."""
    print("Logging in to Empower Retirement...")
    driver.get(EMPOWER_RETIREMENT_LOGIN_URL)
    driver.wait_for_element("#usernameInput", wait=30)
    reject_cookies = driver.select("#onetrust-reject-all-handler", wait=5)
    if reject_cookies:
        reject_cookies.click()
    driver.select("#usernameInput").type(EMPOWER_RETIREMENT_USERNAME)
    driver.select("#passwordInput").type(EMPOWER_RETIREMENT_PASSWORD)
    driver.short_random_sleep()
    driver.select("#submit-login-button").click()

    prompted = False
    for attempt in range(60):
        driver.sleep(5)
        # The login app lives at /participant/, and its code screens are hash
        # routes there; signing in moves on to another app like /participant/home/.
        state = driver.run_js(
            """
            const box = document.querySelector('#remember-device-checkbox');
            if (box && !box.checked) box.click();
            const alerts = [...document.querySelectorAll('[role="alert"], .error-block')];
            return {
                path: location.pathname,
                route: location.hash,
                error: alerts.map((el) => el.innerText.trim()).join(' ').trim(),
            };
            """
        )
        if state["path"] != "/participant/":
            return
        if re.search(r"mfa|verifycode|activationcode", state["route"], re.IGNORECASE):
            if not prompted:
                print(
                    "\n  >> Empower wants a verification code. In the browser window, pick\n"
                    "     text and enter the code. 'Remember device' is ticked for you,\n"
                    "     so later syncs shouldn't ask.\n"
                )
                prompted = True
        elif state["route"].startswith("#/login") and attempt >= 5:
            raise ValueError(
                "Empower didn't get past the login page: "
                + (state["error"] or "check the username and password")
            )

    raise TimeoutError("Timed out waiting for the Empower login to complete")


def fetch_json(driver: Driver, path: str, params: dict[str, Any]) -> Any:
    """GET a participant API endpoint, authenticated like the portal."""
    response = driver.run_js(
        """
        return fetch(args.url, {
            credentials: 'include',
            cache: 'no-store',
            headers: {Accept: 'application/json, text/plain, */*'},
        }).then(async (r) => ({status: r.status, body: await r.text()}));
        """,
        {"url": f"{API_URL}/{path}?{urlencode(params)}"},
    )
    if response["status"] != 200:
        raise ValueError(
            f"Empower request to {path} failed ({response['status']}): "
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
def get_history(driver: Driver, params: dict[str, str]) -> dict[str, Any]:
    """Log in and fetch the transaction history, while the browser is still open.

    Also fetches each contribution's breakdown by money source, which is what
    tells a paycheck contribution apart from money moved in from elsewhere.
    """
    login(driver)
    history = fetch_json(driver, "transactionhistory/summary", params)
    contribution_events = {
        row["eventId"] for row in history if row["category"] in CONTRIBUTION_CATEGORIES
    }
    sources = {
        event_id: fetch_json(
            driver,
            "transactionHistoryDetails/contributions",
            {"gaId": params["gaId"], "indId": params["indId"], "eventId": event_id},
        )
        for event_id in contribution_events
    }
    return {"history": history, "sources": sources}


def parse_contributions(
    history: list[dict[str, Any]],
    sources: dict[int, list[dict[str, Any]]],
    account_name: str,
) -> TransactionLog:
    """
    Parse the paycheck contributions out of the transaction history.

    Each paycheck appears as an "Employee Contribution" and an "Employer
    Contribution" row sharing an event. Empower only gives a payroll date to
    money that came out of a paycheck, so contributions without one, like a
    rollover or a balance moved over from a previous plan, are left out:
    they aren't income, and Monarch counted them where they were first saved.
    """
    payroll_events = {
        event_id
        for event_id, event_sources in sources.items()
        if any(source.get("payrollDate") for source in event_sources)
    }

    transactions = []
    for row in history:
        if row["category"] not in CONTRIBUTION_CATEGORIES:
            continue
        if row["eventId"] not in payroll_events:
            print(
                f"Skipping {row['transactionDesc']} of ${row['amount']:,.2f} on "
                f"{row['effdate']}, which has no payroll date"
            )
            continue

        transactions.append(
            Transaction(
                date=datetime.strptime(row["effdate"], "%d-%b-%Y").date().isoformat(),
                user_account=account_name,
                counterparty_account=row["transactionDesc"],
                amount=row["amount"],
            )
        )

    return TransactionLog(transactions=transactions)


def get_empower_retirement_contributions(
    account_name: str, days: int = HISTORY_DAYS
) -> TransactionLog:
    """Get the last `days` of paycheck contributions to the plan
    EMPOWER_RETIREMENT_TRANSACTIONS_URL points at."""
    # Parse first so a bad URL fails before we open a browser
    params = parse_account_url(EMPOWER_RETIREMENT_TRANSACTIONS_URL)
    today = date.today()
    params["startDate"] = (today - timedelta(days=days)).strftime("%d-%b-%Y")
    params["endDate"] = today.strftime("%d-%b-%Y")

    result = get_history(params)
    if not result:
        raise ValueError("Could not fetch the Empower transaction history")

    return parse_contributions(result["history"], result["sources"], account_name)
