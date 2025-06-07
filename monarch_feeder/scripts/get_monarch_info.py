import asyncio
import json

from monarch_feeder.monarch import login


async def main(
    accounts_file: str = "monarch_accounts.json",
    categories_file: str = "monarch_categories.json",
):
    mm = await login()
    accounts = await mm.get_accounts()
    categories = await mm.get_transaction_categories()
    with open(accounts_file, "w") as f:
        json.dump(accounts, f, indent=2)

    with open(categories_file, "w") as f:
        json.dump(categories, f, indent=2)

    print(f"Account metadata saved to {accounts_file}")
    print(f"Transaction categories saved to {categories_file}")


if __name__ == "__main__":
    asyncio.run(main())
