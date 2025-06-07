from jinja2 import Template

login = Template(
    """
    1. Open the Firefox browser.
    2. Click on the address bar and visit the URL {{ base_url }}.
    3. Use the credentials provided below to log in to the website.

    <robot_credentials>
    Email: {{ email }}
    Password: {{ password }}
    </robot_credentials>

    4. Click on the "Email" form and fill in the field with the email from the credentials above. Click on the "Continue" button.
    5. Click on the "Password" form and fill in the field with the password from the credentials above. Click on the "Sign In" button.
    6. If at any point, there is a captcha, please resolve it yourself by clicking where needed.
    7. If you see multiple options for companies, choose {{ employer_name }}.
    8. When you reach the 2FA/OTP prompt:
       - Call the generate_otp tool with service="rippling"
       - Enter the OTP code from the tool response into the 2FA field
       - Click "Verify" to complete authentication. If for some reason the OTP is not working, you can try again by calling the generate_otp tool once again.
    9. Then, click on the address bar and visit the URL {{ hsa_dashboard_url }}. 
    10. Look for a button labeled "Log in to your HSA account" and click on it. 
        This will open a new tab and after a few seconds, you will see a page with different benefit accounts (e.g. HSA, PKG, TRN, etc).
    11. It is possible that you instead see a page that prompts you to login again. 
        If this happens, exit the tab, and in the previous tab, click on the "Log in to your HSA account" button again so that you see the benefit accounts.
    """
)

hsa_transactions = Template(
    """
    1. Navigate to the URL {{ hsa_transactions_url }}. Scroll down to the "Activity" section.
    2. Click on the "Type: All" dropdown and click on all the options EXCEPT for "Investment". 
    3. Parse each transaction and return a JSON list of dictionaries with the following fields:
        - date (string): Use YYYY-MM-DD format.
        - user_account (string): The HSA account. Always fill this in as "Elevate UMB - {{ employer_name }} HSA".
        - counterparty_account (string): The other account in this transaction.
            Use the description of the transaction as the counterparty account.
        - amount (float): The amount of the transaction.
    4. Return only the JSON list in your response, with no other text. 
    """
)

hsa_portfolio = Template(
    """
    1. Navigate to the URL {{ hsa_portfolio_url }}.
    2. Scroll down to the "Funds" section and click on the "View Details" button.
    3. Parse each holding in the expanded "Funds" section and return a JSON list of dictionaries with the following fields:
        - stock_ticker (string): The stock ticker symbol
        - shares (float): The number of shares held. Make sure that you report the number of shares, not any dollar value.
    4. Return only the JSON list in your response, with no other text.
    """
)

commuter_benefits = Template(
    """
    1. Navigate to the URL {{ commuter_benefits_url }}.
    2. Scroll down to the "Activity" section.
    3. Parse each transaction and return a JSON list of dictionaries with the following fields:
        - date (string): Use YYYY-MM-DD format.
        - user_account (string): The commuter account. Always fill this in as "{{ employer_name }} Commuter Benefit - Rippling".
        - counterparty_account (string): The other account in this transaction.
            Use the description of the transaction as the counterparty account.
        - amount (float): The amount of the transaction.
    4. Return only the JSON list in your response, with no other text. 
    """
)
