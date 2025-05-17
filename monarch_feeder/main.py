import asyncio

from monarchmoney import MonarchMoney


async def main():
    mm = MonarchMoney()

    await mm.interactive_login(use_saved_session=False, save_session=True)

    accounts = await mm.get_accounts()
    print(accounts)


if __name__ == "__main__":
    asyncio.run(main())
