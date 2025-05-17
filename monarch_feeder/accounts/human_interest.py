import datetime
import os
import re
from typing import List, Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from monarch_feeder.core import INVESTMENTS, Transaction

load_dotenv()


class HumanInterestSession:
    """A session for interacting with Human Interest"""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.account_id = None

    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


def login() -> HumanInterestSession:
    """Login to Human Interest

    Returns:
        A session object for subsequent requests
    """
    username = os.environ.get("HUMAN_INTEREST_EMAIL")
    password = os.environ.get("HUMAN_INTEREST_PASSWORD")

    if not username or not password:
        raise ValueError(
            "Username and password must be provided via environment variables"
            "HUMAN_INTEREST_EMAIL and HUMAN_INTEREST_PASSWORD"
        )

    print("Creating session")
    session = HumanInterestSession()
    session.__enter__()
    print("Navigating to login page")

    # Navigate to login page
    session.page.goto("https://app.humaninterest.com/login")
    session.page.wait_for_load_state("networkidle")
    print("Login page loaded")

    # Step 1: Enter email and click next
    email_selector = 'input[data-testid="input-login-email"]'
    session.page.wait_for_selector(email_selector, state="visible")
    print("Email selector found")
    session.page.fill(email_selector, username)
    print("Email filled")

    submit_selector = 'button[data-testid="btn-login-email-submit"]'
    session.page.wait_for_selector(submit_selector, state="visible")
    print("Email submit selector found")
    session.page.click(submit_selector)
    print("Email submit clicked")

    # Step 2: Enter password and submit
    password_selector = 'input[data-testid="input-login-password"]'
    session.page.wait_for_selector(password_selector, state="visible")
    print("Password selector found")
    session.page.fill(password_selector, password)
    print("Password filled")

    signin_selector = 'button[data-testid="btn-login-submit"]'
    session.page.wait_for_selector(signin_selector, state="visible")
    print("Signin selector found")
    session.page.click(signin_selector)
    print("Signin clicked")

    # Step 2.5: Wait for navigation after login
    session.page.wait_for_load_state("networkidle")

    # Step 3: Extract account ID from URL or page content
    session.page.wait_for_selector('a[href*="account/"]')
    print("Account link found")

    # Find links with account IDs
    account_links = session.page.query_selector_all('a[href*="account/"]')
    if account_links:
        href = account_links[0].get_attribute("href")
        match = re.search(r"account/([0-9a-f-]+)", href)
        if match:
            session.account_id = match.group(1)

    if not session.account_id:
        raise Exception("Could not determine account ID after login")

    return session


def _parse_transaction_text(text: str) -> List[Transaction]:
    """Parse transaction text into Transaction objects"""
    # Example: "You contributed $207.69 and your employer contributed $207.69 for a total of 415.38 on pay date 05/02/2025"
    pattern = r"You contributed \$([0-9.]+) and your employer contributed \$([0-9.]+) for a total of [0-9.]+ on pay date (\d{2}/\d{2}/\d{4})"
    match = re.search(pattern, text)

    if not match:
        return []

    employee_amount = float(match.group(1))
    employer_amount = float(match.group(2))
    date_str = match.group(3)

    # Parse date
    date = datetime.datetime.strptime(date_str, "%m/%d/%Y").date()

    # Create two transactions: one for employee contribution, one for employer
    transactions = [
        Transaction(
            date=date,
            amount=employee_amount,
            from_account="Personal",
            to_account="Human Interest 401k",
            description="Employee contribution",
        ),
        Transaction(
            date=date,
            amount=employer_amount,
            from_account="Employer",
            to_account="Human Interest 401k",
            description="Employer contribution",
        ),
    ]

    return transactions


def get_transactions(
    session: Optional[HumanInterestSession] = None,
) -> List[Transaction]:
    """Get all recent transactions from Human Interest

    Args:
        session: An active Human Interest session. If None, will create a new one.

    Returns:
        List of Transaction objects
    """
    close_session = False
    if session is None:
        session = login()
        close_session = True

    try:
        # Navigate to activity page
        session.page.goto(
            f"https://app.humaninterest.com/account/{session.account_id}/activity"
        )
        session.page.wait_for_load_state("networkidle")

        # Find transaction elements
        transaction_elements = session.page.query_selector_all("div.activity-item")

        all_transactions = []
        for elem in transaction_elements:
            text = elem.inner_text()
            transactions = _parse_transaction_text(text)
            all_transactions.extend(transactions)

        return all_transactions

    finally:
        if close_session:
            session.__exit__(None, None, None)


def get_investments(session: Optional[HumanInterestSession] = None) -> INVESTMENTS:
    """Get all investments from Human Interest

    Args:
        session: An active Human Interest session. If None, will create a new one.

    Returns:
        Dictionary mapping fund ticker symbols to number of shares
    """
    close_session = False
    if session is None:
        session = login()
        close_session = True

    try:
        # Navigate to portfolio page
        session.page.goto(
            f"https://app.humaninterest.com/account/{session.account_id}/portfolio"
        )
        session.page.wait_for_load_state("networkidle")

        investments = {}

        # Find fund rows in the table
        fund_rows = session.page.query_selector_all("tr:has(td)")

        for row in fund_rows:
            # Skip rows that don't have fund information
            cells = row.query_selector_all("td")
            if len(cells) < 4:
                continue

            fund_text = cells[0].inner_text().strip()
            shares_text = cells[2].inner_text().strip()

            # Extract ticker symbol (e.g., "VTSAX" from "Vanguard Total Stock Mkt Idx Adm VTSAX")
            ticker_match = re.search(r"([A-Z]{4,5})$", fund_text)
            if not ticker_match:
                continue

            ticker = ticker_match.group(1)

            try:
                shares = float(shares_text.replace(",", ""))
                investments[ticker] = shares
            except ValueError:
                # Skip if shares can't be parsed as a float
                continue

        return investments

    finally:
        if close_session:
            session.__exit__(None, None, None)


if __name__ == "__main__":
    session = login()
