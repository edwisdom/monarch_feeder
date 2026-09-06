import asyncio
import json

from monarch_feeder.monarch import login


async def main(
    accounts_file: str = "monarch_accounts.json",
    categories_file: str = "monarch_categories.json",
):
    mm = await login()
    accounts_data = await mm.get_accounts()
    categories_data = await mm.get_transaction_categories()

    filtered_accounts = []
    for account in accounts_data.get("accounts", []):
        filtered_account = {
            "id": account.get("id"),
            "displayName": account.get("displayName"),
            "displayBalance": account.get("displayBalance"),
            "transactionsCount": account.get("transactionsCount"),
            # Manual accounts have no institution at all
            "institutionName": (account.get("institution") or {}).get("name"),
        }
        filtered_accounts.append(filtered_account)

    filtered_categories = []
    for category in categories_data.get("categories", []):
        filtered_category = {
            "id": category.get("id"),
            "name": category.get("name"),
            "groupName": (category.get("group") or {}).get("name"),
        }
        filtered_categories.append(filtered_category)

    with open(accounts_file, "w") as f:
        json.dump({"accounts": filtered_accounts}, f, indent=2)

    with open(categories_file, "w") as f:
        json.dump({"categories": filtered_categories}, f, indent=2)

    print(f"Account metadata saved to {accounts_file}")
    print(f"Transaction categories saved to {categories_file}")


if __name__ == "__main__":
    asyncio.run(main())
