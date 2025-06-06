import os

import oathtool
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get the MFA secret key
monarch_secret_key = os.environ["MONARCH_MFA_SECRET"]
rippling_secret_key = os.environ["RIPPLING_MFA_SECRET"]

try:
    # Generate OTP
    otp = oathtool.generate_otp(monarch_secret_key)
    print(f"Generated Monarch OTP: {otp}")
    print("OTP generation successful")

    otp = oathtool.generate_otp(rippling_secret_key)
    print(f"Generated Rippling OTP: {otp}")
    print("OTP generation successful")

    # Hint about comparing
    print("\nCompare these OTPs with what you see in your authenticator app.")
    print("If they don't match, your MFA secret key might be in the wrong format.")
except Exception as e:
    print(f"Error generating OTP: {e}")
    print(
        "\nThis suggests your MFA secret key might be in the wrong format or structure."
    )
