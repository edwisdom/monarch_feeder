"""
Example usage of ProgrammaticRunner with Human Interest prompts.
Demonstrates sequential subtasks with selective output saving.
"""

import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv

# Use relative imports within the computer_use_demo module
from .programmatic_runner import ProgrammaticRunner
from .prompts.HUMAN_INTEREST_PROMPTS import login, portfolio, transactions

load_dotenv()


async def main():
    """Example of running Human Interest automation with sequential subtasks."""

    # Initialize the runner
    api_key = os.getenv("ANTHROPIC_API_KEY")
    runner = ProgrammaticRunner(
        api_key=api_key,
        output_dir="./human_interest_outputs",
        screenshots_dir="./human_interest_screenshots",
    )

    # Configuration for Human Interest
    base_url = os.getenv("HUMAN_INTEREST_BASE_URL")
    email = os.getenv("HUMAN_INTEREST_EMAIL")
    password = os.getenv("HUMAN_INTEREST_PASSWORD")
    transactions_url = os.getenv("HUMAN_INTEREST_TRANSACTIONS_URL")
    portfolio_url = os.getenv("HUMAN_INTEREST_PORTFOLIO_URL")

    # Create subtasks
    subtasks = [
        # Login subtask - no output saving needed
        runner.create_subtask(
            name="login",
            prompt=login.render(base_url=base_url, email=email, password=password),
            save_output=False,
            description="Login to Human Interest account",
        ),
        # Transactions subtask - save JSON output
        runner.create_subtask(
            name="get_transactions",
            prompt=transactions.render(transactions_url=transactions_url),
            save_output=True,
            output_filename=f"transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            description="Extract transaction data as JSON",
        ),
        # Portfolio subtask - save JSON output
        runner.create_subtask(
            name="get_portfolio",
            prompt=portfolio.render(portfolio_url=portfolio_url),
            save_output=True,
            output_filename=f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            description="Extract portfolio holdings as JSON",
        ),
    ]

    # Create the task
    task = runner.create_task(
        name="human_interest_data_extraction",
        subtasks=subtasks,
        description="Extract transactions and portfolio data from Human Interest",
        max_tokens=4096,
        only_n_most_recent_images=3,
    )

    # Execute the task
    print("Starting Human Interest data extraction...")
    result = await runner.execute_task(task)

    # Save detailed results
    runner.save_detailed_result(result)

    # Print summary
    print(f"\nTask completed: {result.success}")
    print(f"Duration: {result.duration_seconds:.2f} seconds")
    print(f"Subtasks executed: {len(result.subtask_results)}")

    for subtask_result in result.subtask_results:
        print(
            f"  - {subtask_result.subtask_name}: {'✓' if subtask_result.success else '✗'}"
        )
        if subtask_result.saved_output_path:
            print(f"    Output saved to: {subtask_result.saved_output_path}")
        if subtask_result.error:
            print(f"    Error: {subtask_result.error}")

    if result.final_screenshot_path:
        print(f"Final screenshot: {result.final_screenshot_path}")


if __name__ == "__main__":
    asyncio.run(main())
