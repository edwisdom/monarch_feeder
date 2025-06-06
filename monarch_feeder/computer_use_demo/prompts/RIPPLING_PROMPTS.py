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
    7. Then, you will see the option between "Espresso AI" and "Bigeye" — choose "Espresso AI".
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
