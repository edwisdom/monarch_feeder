#!/usr/bin/env python3
import asyncio
import os
from typing import Any

import pyotp
from dotenv import load_dotenv
from monarchmoney import MonarchMoney

load_dotenv(".env", override=True)


async def verify_session(mm: MonarchMoney) -> bool:
    try:
        subscription = await mm.get_subscription_details()
        print("Successfully verified session after login!")
        print(f"Subscription status: {subscription.get('status', 'unknown')}")
        return True
    except Exception as e:
        print(f"Failed to verify session: {type(e).__name__}: {e}")
        return False


async def login() -> MonarchMoney:

    mm = MonarchMoney()

    # If the session file exists, try to load it and verify the session
    if os.path.exists(mm._session_file):
        print("Loading existing session")
        mm.load_session()
        if await verify_session(mm):
            print("Existing session verified")
            return mm
        else:
            print("Existing session not verified, deleting")
            mm.delete_session()

    # Otherwise, perform a fresh login
    print("Performing fresh login")
    email = os.environ.get("MONARCH_EMAIL")
    password = os.environ.get("MONARCH_PASSWORD")
    secret = os.environ.get("MONARCH_MFA_SECRET")
    totp_uri = (
        f"otpauth://totp/Monarch%20Money:{email}?secret={secret}&issuer=Monarch%20Money"
    )
    code = pyotp.parse_uri(totp_uri).now()
    print(f"Using code: {code}")
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


async def get_transactions_for_account(mm: MonarchMoney, account_id: str) -> Any:
    accounts = await mm.get_accounts()
    print(accounts)


async def main():
    pass


if __name__ == "__main__":
    asyncio.run(main())
