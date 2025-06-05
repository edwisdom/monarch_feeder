from jinja2 import Template

login = Template(
    """
    1. Open the Firefox browser.
    2. Click on the address bar and visit the following URL: {{ base_url }}
    3. Use the credentials provided below to log in to the website.
    
    <robot_credentials>
    Email: {{ email }}
    Password: {{ password }}
    </robot_credentials>
    
    4. Click on the "Email" form and fill in the field with the email from the credentials above. Click on the "Next" button.
    5. Click on the "Password" form and fill in the field with the password from the credentials above. Click on the "Sign In" button.
    """
)

transactions = Template(
    """
    1. Click on the address bar and visit the following URL: {{ transactions_url }}
    2. Scroll down until you can see the latest transactions.
    3. Ignore any transactions labeled as "Trade." Do not click on any other elements on this page.
    4. Parse each transaction and return a JSON list of dictionaries with the following fields:
        - date (string): Use YYYY-MM-DD format.
        - user_account (string): The 401k user account. Always fill this in as "Human Interest - Espresso 401k".
        - counterparty_account (string): The other account in this transaction.
            Make sure this is separate for employee vs. employer vs. rollover contributions.
        - amount (float): The amount of the transaction.
    5. Return only the JSON list in your response, with no other text. 
    """
)

portfolio = Template(
    """
    1. Click on the address bar and visit the following URL: {{ portfolio_url }}
    2. Scroll down until you can see the portfolio holdings. 
    3. Parse each holding and return a JSON list of dictionaries with the following fields:
        - stock_ticker (string): The stock ticker symbol
        - shares (float): The number of shares held. Make sure that you report the number of shares, not the dollar value.
    4. Ignore the US vs. international subtotals and do not include them in your response.
    5. Return only the JSON list in your response, with no other text.
    """
)
