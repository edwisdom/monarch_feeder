"""
Generic automation orchestrator for running multiple computer use automations.
Replaces individual automation modules with a configurable, extensible solution.
"""

import asyncio
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Callable, List

from dotenv import load_dotenv

from .programmatic_runner import ProgrammaticRunner, SubTask, TaskConfig

# Load environment variables
load_dotenv()


class AutomationType(Enum):
    """Supported automation types."""

    HUMAN_INTEREST = "human_interest"


def create_human_interest_task() -> TaskConfig:
    """Create Human Interest automation task configuration."""
    from .prompts.HUMAN_INTEREST_PROMPTS import login, portfolio, transactions

    base_url = os.getenv("HUMAN_INTEREST_BASE_URL")
    email = os.getenv("HUMAN_INTEREST_EMAIL")
    password = os.getenv("HUMAN_INTEREST_PASSWORD")
    transactions_url = os.getenv("HUMAN_INTEREST_TRANSACTIONS_URL")
    portfolio_url = os.getenv("HUMAN_INTEREST_PORTFOLIO_URL")

    subtasks = [
        SubTask(
            name="login",
            prompt=login.render(
                base_url=base_url,
                email=email,
                password=password,
            ),
            save_output=False,
            description="Log into Human Interest platform",
        ),
        SubTask(
            name="portfolio",
            prompt=portfolio.render(portfolio_url=portfolio_url),
            save_output=True,
            description="Extract portfolio information",
        ),
        SubTask(
            name="transactions",
            prompt=transactions.render(transactions_url=transactions_url),
            save_output=True,
            description="Extract transaction history",
        ),
    ]

    return TaskConfig(
        name="human_interest",
        description="Extract data from Human Interest 401k platform",
        subtasks=subtasks,
    )


# Mapping from automation types to their task creation functions
AUTOMATION_TASK_CREATORS: dict[AutomationType, Callable[[], TaskConfig]] = {
    AutomationType.HUMAN_INTEREST: create_human_interest_task,
}


class AutomationOrchestrator:
    """Orchestrates multiple automation tasks sequentially."""

    def __init__(
        self,
        api_key: str,
        base_output_dir: str = "./automation_outputs",
        base_screenshots_dir: str = "./automation_screenshots",
    ):
        self.api_key = api_key
        self.base_output_dir = Path(base_output_dir)
        self.base_screenshots_dir = Path(base_screenshots_dir)

    def _create_automation_directories(
        self, automation_type: AutomationType
    ) -> tuple[str, str]:
        """Create and return automation-specific output directories."""
        automation_name = automation_type.value

        output_dir = self.base_output_dir / automation_name
        screenshots_dir = self.base_screenshots_dir / automation_name

        # Create directories if they don't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        return str(output_dir), str(screenshots_dir)

    def _parse_automation_type(self, automation_name: str) -> AutomationType:
        """Parse automation name string to AutomationType enum."""
        try:
            return AutomationType(automation_name)
        except ValueError:
            available = [automation.value for automation in AutomationType]
            raise ValueError(
                f"Unknown automation: {automation_name}. "
                f"Available automations: {', '.join(available)}"
            )

    def _create_task_for_automation(
        self, automation_type: AutomationType
    ) -> TaskConfig:
        """Create a task configuration for the given automation type."""
        creator_func = AUTOMATION_TASK_CREATORS.get(automation_type)
        if not creator_func:
            raise ValueError(f"No task creator found for {automation_type.value}")
        return creator_func()

    async def run_automations(self, automation_names: List[str]) -> None:
        """Run multiple automations by name."""
        if not automation_names:
            print("❌ No automations specified")
            sys.exit(1)

        print(
            f"🚀 Starting {len(automation_names)} automation(s): {', '.join(automation_names)}"
        )
        print("⏱️  This may take several minutes to complete")
        print()

        # Execute all tasks sequentially
        all_results = []

        for name in automation_names:
            try:
                automation_type = self._parse_automation_type(name)
                task = self._create_task_for_automation(automation_type)

                # Create automation-specific directories
                output_dir, screenshots_dir = self._create_automation_directories(
                    automation_type
                )

                print(f"📁 {automation_type.value} outputs will be saved to:")
                print(f"   - {output_dir}/")
                print(f"   - {screenshots_dir}/")
                print()

                # Create a runner specific to this automation
                runner = ProgrammaticRunner(
                    api_key=self.api_key,
                    output_dir=output_dir,
                    screenshots_dir=screenshots_dir,
                )

                # Execute this automation's tasks
                results = await runner.execute_tasks([task])
                all_results.extend(results)

            except ValueError as e:
                print(f"❌ {e}")
                sys.exit(1)

        # Print summary
        print("\n" + "=" * 60)
        print("🎯 AUTOMATION SUMMARY")
        print("=" * 60)

        for result in all_results:
            status = "✅ SUCCESS" if result.success else "❌ FAILED"
            duration = f"{result.duration_seconds:.1f}s"
            print(f"{status} | {result.task_name} ({duration})")

            # Show subtask results
            for subtask in result.subtask_results:
                subtask_status = "✓" if subtask.success else "✗"
                print(f"  {subtask_status} {subtask.subtask_name}")
                if subtask.saved_output_path:
                    print(f"    📁 {subtask.saved_output_path}")

        # Show overall status
        total_success = all(result.success for result in all_results)
        overall_status = (
            "🎉 ALL AUTOMATIONS COMPLETED SUCCESSFULLY"
            if total_success
            else "⚠️  SOME AUTOMATIONS FAILED"
        )
        print(f"\n{overall_status}")


async def main():
    """Main entry point for automation orchestrator."""
    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not found in environment")
        sys.exit(1)

    # Parse automation list from environment or command line
    automation_list = os.getenv("AUTOMATION_LIST", "human_interest")
    automations = [name.strip() for name in automation_list.split(",")]

    # Allow command line override
    if len(sys.argv) > 1:
        automations = sys.argv[1:]

    print(f"🔧 Requested automations: {automations}")

    # Create orchestrator and run
    orchestrator = AutomationOrchestrator(api_key=api_key)
    await orchestrator.run_automations(automations)


if __name__ == "__main__":
    asyncio.run(main())
