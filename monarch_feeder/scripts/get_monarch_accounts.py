import asyncio
import json

from monarch_feeder.monarch import login


async def main(output_file: str = "monarch_accounts.json"):
    mm = await login()
    accounts = await mm.get_accounts()
    with open(output_file, "w") as f:
        json.dump(accounts, f, indent=2)

    print(f"Formatted JSON saved to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
