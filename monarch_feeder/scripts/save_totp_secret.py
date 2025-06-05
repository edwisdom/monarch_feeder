from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, TypeAlias
from urllib.parse import parse_qs, urlparse

import pyzbar.pyzbar as pyzbar
from PIL import Image

from monarch_feeder.auth.otpauth_migrate import parse
from monarch_feeder.scripts.utils import update_env_variable

BASE_DIR = Path(".auth")


class AuthProtocol(Enum):
    GOOGLE_AUTHENTICATOR = "google_authenticator"
    TWILIO_AUTHY = "twilio_authy"


def extract_data_from_qr_code(filename: Path, debug: bool = False) -> str | None:
    img = Image.open(BASE_DIR / filename)
    decoded_objects = pyzbar.decode(img)

    if not decoded_objects:
        print("Could not decode QR code")
        return None

    data = decoded_objects[0].data.decode("utf-8")

    if debug:
        print("\nQR Code Data:")
        print("------------")
        print(data)

    return data


def extract_google_authenticator_secret(data: str) -> str | None:
    try:
        # Use otpauth_migrate and complicated protobuf parsing to parse the data
        secret = parse(data)
        return secret
    except Exception as e:
        print(f"\nError decoding data: {e}")
        return None


def extract_twilio_authy_secret(data: str) -> str | None:
    try:
        parsed_url = urlparse(data)
        query_params = parse_qs(parsed_url.query)
        if "secret" in query_params:
            secret = query_params["secret"][0]
            return secret
        else:
            print("No secret parameter found in otpauth URL")
            return None
    except Exception as e:
        print(f"\nError decoding data: {e}")
        return None


DATA_PREFIX_TO_PROTOCOL: dict[str, AuthProtocol] = {
    "otpauth-migration://": AuthProtocol.GOOGLE_AUTHENTICATOR,
    "otpauth://": AuthProtocol.TWILIO_AUTHY,
}
SECRET_EXTRACTOR: TypeAlias = Callable[[str], str | None]
AUTH_PROTOCOL_TO_EXTRACTOR: dict[AuthProtocol, SECRET_EXTRACTOR] = {
    AuthProtocol.GOOGLE_AUTHENTICATOR: extract_google_authenticator_secret,
    AuthProtocol.TWILIO_AUTHY: extract_twilio_authy_secret,
}


def extract_totp_secret(filename: str, debug: bool = False) -> str | None:
    data = extract_data_from_qr_code(filename, debug)

    if not data:
        return None

    # Determine auth protocol based on data prefix
    auth_protocol = None
    for prefix, protocol in DATA_PREFIX_TO_PROTOCOL.items():
        if data.startswith(prefix):
            auth_protocol = protocol
            break

    if auth_protocol is None:
        print(f"\nUnsupported QR code format. Data starts with: {data[:50]}...")
        return None

    extractor = AUTH_PROTOCOL_TO_EXTRACTOR[auth_protocol]
    return extractor(data)


@dataclass
class AuthInfo:
    source_path: Path
    destination_secret_name: str


SUPPORTED_AUTHS = [
    AuthInfo(
        source_path=Path("monarch_mfa_auth_qr.png"),
        destination_secret_name="MONARCH_MFA_SECRET",
    ),
    AuthInfo(
        source_path=Path("rippling_mfa_auth_qr.png"),
        destination_secret_name="RIPPLING_MFA_SECRET",
    ),
]

if __name__ == "__main__":
    for auth_info in SUPPORTED_AUTHS:
        secret = extract_totp_secret(auth_info.source_path)
        if secret:
            print(
                f"Saving secret for {auth_info.source_path} at .env var {auth_info.destination_secret_name}"
            )
            update_env_variable(auth_info.destination_secret_name, secret)
        else:
            print(f"No secret found for {auth_info.source_path}")
