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
        # Enable JavaScript and other browser features needed for SPAs
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--enable-javascript",
            ],
        )
        # Create context with JavaScript enabled
        self.context = self.browser.new_context(
            java_script_enabled=True, ignore_https_errors=True
        )
        self.page = self.context.new_page()
        # Set longer timeout for SPA interactions
        self.page.set_default_timeout(30000)  # 30 seconds
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

    # Screenshot 1: Initial login page
    session.page.screenshot(path="debug_01_login_page.png")
    print("Screenshot saved: debug_01_login_page.png")

    # Step 1: Enter email and click next
    email_selector = 'input[data-testid="input-login-email"]'
    session.page.wait_for_selector(email_selector, state="visible")
    print("Email selector found")
    session.page.fill(email_selector, username)
    print("Email filled")

    # Screenshot 2: After filling email
    session.page.screenshot(path="debug_02_email_filled.png")
    print("Screenshot saved: debug_02_email_filled.png")

    submit_selector = 'button[data-testid="btn-login-email-submit"]'
    session.page.wait_for_selector(submit_selector, state="visible")
    print("Email submit selector found")

    # Try multiple ways to submit the form since SPAs can be finicky
    try:
        # Method 1: Try pressing Enter in the email field (most reliable for SPAs)
        session.page.focus(email_selector)
        session.page.keyboard.press("Enter")
        print("Pressed Enter on email field")
        session.page.wait_for_timeout(2000)  # Give time for submission

        # Check if password field appeared
        password_selector = 'input[name="password"][type="password"]'
        try:
            session.page.wait_for_selector(
                password_selector, state="visible", timeout=3000
            )
            print("Password field appeared after pressing Enter")
            # Screenshot 3a: Success with Enter method
            session.page.screenshot(path="debug_03a_enter_success.png")
            print("Screenshot saved: debug_03a_enter_success.png")
        except:
            print("Enter method didn't work, trying click with wait for response...")
            # Screenshot 3b: After Enter attempt failed
            session.page.screenshot(path="debug_03b_enter_failed.png")
            print("Screenshot saved: debug_03b_enter_failed.png")

            # Method 2: Click and wait for network response
            with session.page.expect_response(
                lambda response: True, timeout=10000
            ) as response_info:
                session.page.click(submit_selector)
                print("Clicked submit button and waiting for response...")

            session.page.wait_for_timeout(2000)

            # Check again for password field
            try:
                session.page.wait_for_selector(
                    password_selector, state="visible", timeout=3000
                )
                print("Password field appeared after click with response wait")
                # Screenshot 3c: Success with click method
                session.page.screenshot(path="debug_03c_click_success.png")
                print("Screenshot saved: debug_03c_click_success.png")
            except:
                print("Click with response wait didn't work, trying form submission...")
                # Screenshot 3d: After click attempt failed
                session.page.screenshot(path="debug_03d_click_failed.png")
                print("Screenshot saved: debug_03d_click_failed.png")

                # Method 3: Try to submit the form directly
                form_selector = "form"
                try:
                    session.page.eval_on_selector(
                        form_selector, "form => form.submit()"
                    )
                    print("Submitted form directly")
                    session.page.wait_for_timeout(2000)
                    # Screenshot 3e: After form submit
                    session.page.screenshot(path="debug_03e_form_submit.png")
                    print("Screenshot saved: debug_03e_form_submit.png")
                except:
                    print("Direct form submission failed")

                # Method 4: Try JavaScript click
                session.page.eval_on_selector(
                    submit_selector, "element => element.click()"
                )
                print("Tried JavaScript click")
                session.page.wait_for_timeout(2000)
                # Screenshot 3f: After JavaScript click
                session.page.screenshot(path="debug_03f_js_click.png")
                print("Screenshot saved: debug_03f_js_click.png")

    except Exception as e:
        print(f"Error during form submission attempts: {e}")

    # Give JavaScript a moment to process the form submission
    session.page.wait_for_timeout(1000)  # 1 second delay

    print("Waiting for password field to appear...")
    # Wait for the password field to appear instead of just waiting for network idle
    selector = 'input[name="password"][type="password"]'

    password_found = False
    try:
        session.page.wait_for_selector(selector, state="visible", timeout=3000)
        password_selector = selector
        password_found = True
        print(f"Password field found with selector: {selector}")
        # Screenshot 4: Password field found
        session.page.screenshot(path="debug_04_password_field_found.png")
        print("Screenshot saved: debug_04_password_field_found.png")
    except:
        print("Password field still not found after all submission attempts")

        # Take a screenshot to debug
        session.page.screenshot(path="debug_after_email.png")
        print("Screenshot saved as debug_after_email.png")

        # Check for validation errors or messages
        error_selectors = [
            '[data-testid*="error"]',
            ".error",
            ".alert",
            '[role="alert"]',
            ".message",
            ".notification",
        ]

        for error_sel in error_selectors:
            error_elements = session.page.query_selector_all(error_sel)
            if error_elements:
                for elem in error_elements:
                    error_text = elem.inner_text().strip()
                    if error_text:
                        print(f"Found error/message: {error_text}")

        # Check if the email field still has focus/is still visible (indicating no submission happened)
        email_still_present = session.page.is_visible(email_selector)
        print(f"Email field still visible: {email_still_present}")

        # Check current page HTML for any clues
        page_content = session.page.content()
        if "javascript" in page_content.lower():
            print("WARNING: Page content mentions JavaScript - this might be disabled")
        if "error" in page_content.lower():
            print("WARNING: Page content contains 'error'")

        # Debug: Check what input elements are available
        all_inputs = session.page.query_selector_all("input")
        print(f"Found {len(all_inputs)} input elements:")
        for i, input_elem in enumerate(all_inputs):
            test_id = input_elem.get_attribute("data-testid")
            name = input_elem.get_attribute("name")
            input_type = input_elem.get_attribute("type")
            placeholder = input_elem.get_attribute("placeholder")
            value = input_elem.get_attribute("value")
            print(
                f"  Input {i}: data-testid='{test_id}', name='{name}', type='{input_type}', placeholder='{placeholder}', value='{value[:20] if value else None}'"
            )

        # Debug: Check current URL
        current_url = session.page.url
        print(f"Current URL: {current_url}")

        raise Exception("Could not find password field after email submission")

    if not password_found:
        print(f"No password field found with any selector")

        # Take a screenshot to debug
        session.page.screenshot(path="debug_after_email.png")
        print("Screenshot saved as debug_after_email.png")

        # Debug: Check what input elements are available
        all_inputs = session.page.query_selector_all("input")
        print(f"Found {len(all_inputs)} input elements:")
        for i, input_elem in enumerate(all_inputs):
            test_id = input_elem.get_attribute("data-testid")
            name = input_elem.get_attribute("name")
            input_type = input_elem.get_attribute("type")
            placeholder = input_elem.get_attribute("placeholder")
            print(
                f"  Input {i}: data-testid='{test_id}', name='{name}', type='{input_type}', placeholder='{placeholder}'"
            )

        # Debug: Check current URL
        current_url = session.page.url
        print(f"Current URL: {current_url}")

        # Debug: Check page content for error messages
        page_text = session.page.inner_text("body")
        if "javascript" in page_text.lower():
            print("Page mentions JavaScript - this might be the issue")

        raise Exception("Could not find password field after email submission")

    # Step 2: Enter password and submit
    session.page.fill(password_selector, password)
    print("Password filled")

    # Screenshot 5: Password filled
    session.page.screenshot(path="debug_05_password_filled.png")
    print("Screenshot saved: debug_05_password_filled.png")

    signin_selector = 'button[type="submit"]'
    session.page.wait_for_selector(signin_selector, state="visible")
    print("Signin selector found")
    session.page.click(signin_selector)
    print("Signin clicked")

    # Step 2.5: Wait for navigation after login
    session.page.wait_for_load_state("networkidle")

    # Screenshot 6: After login
    session.page.screenshot(path="debug_06_after_login.png")
    print("Screenshot saved: debug_06_after_login.png")

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
