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
       - Click "Verify" to complete authentication
    """
)
