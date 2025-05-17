#!/usr/bin/env python3
#
# Parse Google Authenticator QR codes using protobuf definition from:
# https://alexbakker.me/post/parsing-google-auth-export-qr-code.html

import urllib.parse
from base64 import b32encode, b64decode

from monarch_feeder.auth.otpauth_migrate_pb2 import MigrationPayload


def parse(code: str) -> str:
    # Split out the data field from the 'otpauth-migration' URI
    query = urllib.parse.parse_qsl(code)
    if query:
        path, data = query[0]
        data = b64decode(data)
    else:
        # See if we just got the urldecoded data field
        data = b64decode(code)

    # Unpack protobuf layer
    payload = MigrationPayload.FromString(data)
    if not payload.otp_parameters:
        raise ValueError("No payloads found")
    for parameters in payload.otp_parameters:
        # Print parameters incase the type/algorithm is needed
        print(parameters)

        # Re-encode with base32 for consumption by other tools
        output = b32encode(parameters.secret).decode()
        print(f"Secret code = {output:s}\n")

    return output
