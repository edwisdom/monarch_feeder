import pyzbar.pyzbar as pyzbar
from PIL import Image

from monarch_feeder.auth.otpauth_migrate import parse


def extract_totp_secret():
    # Read the QR code image
    img = Image.open(".auth/monarch_mfa_auth_qr.png")

    # Decode the QR code
    decoded_objects = pyzbar.decode(img)

    if not decoded_objects:
        print("Could not decode QR code")
        return

    # Get the data from the first decoded object
    data = decoded_objects[0].data.decode("utf-8")

    # Print diagnostic information
    print("\nQR Code Data:")
    print("------------")
    print(data)

    # Check if this is a migration QR code
    if data.startswith("otpauth-migration://"):
        try:
            # Use otpauth_migrate to parse the data
            secret = parse(data)
            print(f"\nTOTP Secret: {secret}")
        except Exception as e:
            print(f"\nError decoding data: {e}")
    else:
        print("\nNot a Google Authenticator migration QR code")


if __name__ == "__main__":
    extract_totp_secret()
