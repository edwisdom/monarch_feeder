#!/usr/bin/env python3
import asyncio
import os

import pyotp
from dotenv import load_dotenv
from monarchmoney import MonarchMoney
from monarchmoney.monarchmoney import RequireMFAException

load_dotenv(".env", override=True)


async def verify_session(mm: MonarchMoney) -> bool:
    try:
        subscription = await mm.get_subscription_details()
        print("Successfully verified session after login!")
        print(f"Subscription status: {subscription.get('status', 'unknown')}")
        return True
    except RequireMFAException as e:
        print(f"Failed to verify session after login: {e}")
        return False


async def login() -> MonarchMoney:

    mm = MonarchMoney()

    # If the session file exists, try to load it and verify the session
    if os.path.exists(mm._session_file):
        mm.load_session()
        if await verify_session(mm):
            return mm

    # Otherwise, perform a fresh login
    mm.delete_session()
    email = os.environ.get("MONARCH_EMAIL")
    password = os.environ.get("MONARCH_PASSWORD")
    secret = os.environ.get("MONARCH_MFA_SECRET")
    totp_uri = (
        f"otpauth://totp/Monarch%20Money:{email}?secret={secret}&issuer=Monarch%20Money"
    )
    code = pyotp.parse_uri(totp_uri).now()
    await mm.multi_factor_authenticate(
        email=email,
        password=password,
        code=code,
    )

    # Verify the new session and save it
    if not await verify_session(mm):
        raise Exception("Failed to verify session after fresh login")

    mm.save_session()
    print(f"Saved new session to file {mm._session_file}")

    return mm


if __name__ == "__main__":
    asyncio.run(login())
