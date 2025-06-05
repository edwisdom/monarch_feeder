import os

import oathtool
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get the MFA secret key
mfa_secret_key = os.environ["MONARCH_MFA_SECRET"]

try:
    # Generate OTP
    otp = oathtool.generate_otp(mfa_secret_key)
    print(f"Generated OTP: {otp}")
    print("OTP generation successful")

    # Hint about comparing
    print("\nCompare this OTP with what you see in your authenticator app.")
    print("If they don't match, your MFA secret key might be in the wrong format.")
except Exception as e:
    print(f"Error generating OTP: {e}")
    print(
        "\nThis suggests your MFA secret key might be in the wrong format or structure."
    )
    print(
        "Make sure it's the exact secret key provided when you set up MFA (base32-encoded string)."
    )
