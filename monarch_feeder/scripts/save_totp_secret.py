from pathlib import Path

import pyzbar.pyzbar as pyzbar
from PIL import Image

from monarch_feeder.auth.otpauth_migrate import parse
from monarch_feeder.scripts.utils import update_env_variable

BASE_DIR = Path(".auth")


def extract_totp_secret(filename: str = "monarch_mfa_auth_qr.png", debug: bool = False):
    # Read the QR code image
    img = Image.open(BASE_DIR / filename)

    # Decode the QR code
    decoded_objects = pyzbar.decode(img)

    if not decoded_objects:
        print("Could not decode QR code")
        return

    # Get the data from the first decoded object
    data = decoded_objects[0].data.decode("utf-8")

    # Print diagnostic information
    if debug:
        print("\nQR Code Data:")
        print("------------")
        print(data)

    # Check if this is a migration QR code
    if data.startswith("otpauth-migration://"):
        try:
            # Use otpauth_migrate to parse the data
            secret = parse(data)
            return secret
        except Exception as e:
            print(f"\nError decoding data: {e}")
    else:
        print("\nNot a Google Authenticator migration QR code")


if __name__ == "__main__":
    secret = extract_totp_secret()
    update_env_variable("MONARCH_MFA_SECRET", secret)
