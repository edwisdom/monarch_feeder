"""
Programmatic runner for computer use tasks.
Allows executing pre-defined prompts and saving results without interactive UI.
"""

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam
from pydantic import BaseModel

from .loop import APIProvider, sampling_loop
from .tools import ToolResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("computer_use_execution.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class SubTask:
    """Configuration for a single subtask within a task."""

    name: str
    prompt: str
    save_output: bool = False
    output_filename: Optional[str] = None
    description: str = ""
    clear_session: bool = False
    response_model: BaseModel | None = None


@dataclass
class SubTaskResult:
    """Results from executing a single subtask."""

    subtask_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    messages: List[BetaMessageParam]
    extracted_output: Optional[str] = None
    saved_output_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class TaskConfig:
    """Configuration for a computer use task composed of subtasks."""

    name: str
    description: str
    subtasks: List[SubTask]
    system_prompt_suffix: str = ""
    max_tokens: int = 4096
    model: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    tool_version: str = "computer_use_20250124"
    only_n_most_recent_images: Optional[int] = 3
    thinking_budget: Optional[int] = None
    token_efficient_tools_beta: bool = False
    enable_structured_output: bool = False

    def __post_init__(self):
        """Validate that subtasks is not empty."""
        if not self.subtasks:
            raise ValueError("Tasks must have at least one subtask")


@dataclass
class TaskResult:
    """Results from executing a computer use task."""

    task_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    subtask_results: List[SubTaskResult]
    error: Optional[str] = None
    final_screenshot_path: Optional[str] = None

    @property
    def messages(self) -> List[BetaMessageParam]:
        """Get all messages from all subtasks."""
        all_messages = []
        for subtask_result in self.subtask_results:
            all_messages.extend(subtask_result.messages)
        return all_messages


class ProgrammaticRunner:
    """Runner for executing computer use tasks programmatically."""

    def __init__(
        self,
        api_key: str,
        output_dir: str = "./outputs",
        screenshots_dir: str = "./screenshots",
    ):
        self.api_key = api_key
        self.output_dir = Path(output_dir)
        self.screenshots_dir = Path(screenshots_dir)

        # Create output directories
        self.output_dir.mkdir(exist_ok=True)
        self.screenshots_dir.mkdir(exist_ok=True)

        os.environ["WIDTH"] = "1024"  # XGA width (16:9 aspect ratio)
        os.environ["HEIGHT"] = "768"  # XGA height (16:9 aspect ratio)

        # Track execution state
        self.current_task_name = ""

    def load_tasks_from_file(self, config_file: str) -> List[TaskConfig]:
        """Load task configurations from a JSON file."""
        with open(config_file, "r") as f:
            tasks_data = json.load(f)

        tasks = []
        for task_data in tasks_data.get("tasks", []):
            # Convert subtasks data to SubTask objects
            subtasks_data = task_data.pop("subtasks")
            subtasks = [SubTask(**subtask_data) for subtask_data in subtasks_data]
            task_data["subtasks"] = subtasks

            tasks.append(TaskConfig(**task_data))

        return tasks

    def create_task(self, name: str, subtasks: List[SubTask], **kwargs) -> TaskConfig:
        """Create a task configuration with subtasks."""
        return TaskConfig(
            name=name,
            description=kwargs.get("description", f"Task: {name}"),
            subtasks=subtasks,
            **{k: v for k, v in kwargs.items() if k != "description"},
        )

    def create_subtask(
        self,
        name: str,
        prompt: str,
        save_output: bool = False,
        output_filename: Optional[str] = None,
        description: str = "",
        clear_session: bool = False,
        response_model: BaseModel | None = None,
    ) -> SubTask:
        """Create a subtask configuration."""
        return SubTask(
            name=name,
            prompt=prompt,
            save_output=save_output,
            output_filename=output_filename,
            description=description,
            clear_session=clear_session,
            response_model=response_model,
        )

    async def execute_task(self, task: TaskConfig) -> TaskResult:
        """Execute a computer use task with sequential subtasks."""
        logger.info(f"Starting task: {task.name}")
        start_time = datetime.now()
        self.current_task_name = task.name

        subtask_results = []
        messages: List[BetaMessageParam] = []
        overall_success = True

        try:
            for i, subtask in enumerate(task.subtasks):
                logger.info(
                    f"Starting subtask {i+1}/{len(task.subtasks)}: {subtask.name}"
                )
                subtask_start = datetime.now()

                try:
                    # Prepare messages for this subtask
                    if subtask.clear_session:
                        subtask_messages = []
                        logger.info(f"Clearing session for subtask: {subtask.name}")
                    else:
                        subtask_messages = messages.copy()

                    subtask_messages.append(
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": subtask.prompt}],
                        }
                    )

                    # Execute the sampling loop for this subtask
                    final_messages = await sampling_loop(
                        model=task.model,
                        provider=APIProvider(task.provider),
                        system_prompt_suffix=task.system_prompt_suffix,
                        messages=subtask_messages,
                        output_callback=self._output_callback,
                        tool_output_callback=self._tool_output_callback,
                        api_response_callback=self._api_response_callback,
                        api_key=self.api_key,
                        only_n_most_recent_images=task.only_n_most_recent_images,
                        max_tokens=task.max_tokens,
                        tool_version=task.tool_version,
                        thinking_budget=task.thinking_budget,
                        token_efficient_tools_beta=task.token_efficient_tools_beta,
                        enable_structured_output=task.enable_structured_output,
                        response_model=subtask.response_model,
                    )

                    subtask_end = datetime.now()
                    subtask_duration = (subtask_end - subtask_start).total_seconds()

                    # Extract output if needed
                    extracted_output = None
                    saved_output_path = None

                    if subtask.save_output:
                        extracted_output = self._extract_output_from_messages(
                            final_messages
                        )
                        if extracted_output:
                            saved_output_path = self._save_subtask_output(
                                subtask, extracted_output, subtask_start
                            )

                    # Create subtask result
                    subtask_result = SubTaskResult(
                        subtask_name=subtask.name,
                        success=True,
                        start_time=subtask_start,
                        end_time=subtask_end,
                        duration_seconds=subtask_duration,
                        messages=final_messages,
                        extracted_output=extracted_output,
                        saved_output_path=saved_output_path,
                        error=None,
                    )

                    subtask_results.append(subtask_result)

                    # Update conversation state - only carry forward messages if session wasn't cleared
                    if not subtask.clear_session:
                        messages = final_messages

                    logger.info(
                        f"Subtask completed: {subtask.name} ({subtask_duration:.2f}s)"
                    )

                except Exception as e:
                    subtask_end = datetime.now()
                    subtask_duration = (subtask_end - subtask_start).total_seconds()

                    logger.error(f"Subtask failed: {subtask.name} - {str(e)}")

                    subtask_result = SubTaskResult(
                        subtask_name=subtask.name,
                        success=False,
                        start_time=subtask_start,
                        end_time=subtask_end,
                        duration_seconds=subtask_duration,
                        messages=messages,
                        extracted_output=None,
                        saved_output_path=None,
                        error=str(e),
                    )

                    subtask_results.append(subtask_result)
                    overall_success = False
                    # Continue with next subtask even if this one failed

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Take final screenshot if possible
            final_screenshot_path = self._take_final_screenshot()

            result = TaskResult(
                task_name=task.name,
                success=overall_success,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                subtask_results=subtask_results,
                final_screenshot_path=final_screenshot_path,
            )

            logger.info(
                f"Task completed: {task.name} ({duration:.2f}s) - Success: {overall_success}"
            )
            return result

        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.error(f"Task failed: {task.name} - {str(e)}")

            return TaskResult(
                task_name=task.name,
                success=False,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                subtask_results=subtask_results,
                error=str(e),
                final_screenshot_path=None,
            )

    def _output_callback(self, content: BetaContentBlockParam):
        """Callback for handling model outputs."""
        if content.get("type") == "text":
            logger.info(f"Model output: {content.get('text', '')[:100]}...")

    def _tool_output_callback(self, tool_result: ToolResult, tool_id: str):
        """Callback for handling tool outputs."""
        logger.info(f"Tool executed: {tool_id}")

    def _api_response_callback(self, request, response, error):
        """Callback for handling API responses."""
        pass  # Simplified - no longer tracking API responses

    def _take_final_screenshot(self) -> Optional[str]:
        """Take a final screenshot and save it."""
        try:
            # Import computer tool to take screenshot
            from .tools.computer import ComputerTool20250124

            computer = ComputerTool20250124()

            result = asyncio.run(computer.screenshot())
            if result.output and hasattr(result, "base64_image"):
                screenshot_filename = f"{self.current_task_name}_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                screenshot_path = self.screenshots_dir / screenshot_filename

                import base64

                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(result.base64_image))

                return str(screenshot_path)
        except Exception as e:
            logger.warning(f"Failed to take final screenshot: {e}")

        return None

    def _extract_output_from_messages(
        self, messages: List[BetaMessageParam]
    ) -> Optional[str]:
        """Extract JSON or structured output from the last assistant message."""
        if not messages:
            return None

        # Look for the last assistant message
        for message in reversed(messages):
            if message.get("role") == "assistant":
                content = message.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            # Try to extract JSON from the text
                            json_match = re.search(r"\[.*\]", text, re.DOTALL)
                            if json_match:
                                try:
                                    # Validate it's proper JSON
                                    json.loads(json_match.group())
                                    return json_match.group()
                                except json.JSONDecodeError:
                                    pass
                            # If no JSON found, return the full text
                            return text.strip()
                elif isinstance(content, str):
                    # Handle string content
                    json_match = re.search(r"\[.*\]", content, re.DOTALL)
                    if json_match:
                        try:
                            json.loads(json_match.group())
                            return json_match.group()
                        except json.JSONDecodeError:
                            pass
                    return content.strip()

        return None

    def _save_subtask_output(
        self, subtask: SubTask, output: str, timestamp: datetime
    ) -> str:
        """Save subtask output to file."""
        if subtask.output_filename:
            filename = subtask.output_filename
        else:
            filename = f"{subtask.name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"

        output_path = self.output_dir / filename

        # Try to save as JSON if it's valid JSON, otherwise save as text
        try:
            parsed_json = json.loads(output)
            with open(output_path, "w") as f:
                json.dump(parsed_json, f, indent=2)
        except json.JSONDecodeError:
            # Save as text file
            output_path = output_path.with_suffix(".txt")
            with open(output_path, "w") as f:
                f.write(output)

        logger.info(f"Subtask output saved to: {output_path}")
        return str(output_path)

    async def execute_tasks(self, tasks: List[TaskConfig]) -> List[TaskResult]:
        """Execute multiple tasks in sequence."""
        results = []

        for task in tasks:
            result = await self.execute_task(task)
            results.append(result)

            # Save individual result
            self.save_result(result)

        return results

    def save_result(self, result: TaskResult):
        """Save task result to file."""
        result_filename = (
            f"{result.task_name}_{result.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        )
        result_path = self.output_dir / result_filename

        # Convert result to serializable format
        result_data = {
            "task_name": result.task_name,
            "success": result.success,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat(),
            "duration_seconds": result.duration_seconds,
            "error": result.error,
            "final_screenshot_path": result.final_screenshot_path,
            "subtask_results_count": len(result.subtask_results),
            "messages_count": len(result.messages),
        }

        with open(result_path, "w") as f:
            json.dump(result_data, f, indent=2)

        logger.info(f"Result saved to: {result_path}")

    def save_detailed_result(self, result: TaskResult):
        """Save detailed task result including full messages and tool outputs."""
        result_filename = f"{result.task_name}_detailed_{result.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        result_path = self.output_dir / result_filename

        # Convert result to serializable format
        result_data = {
            "task_name": result.task_name,
            "success": result.success,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat(),
            "duration_seconds": result.duration_seconds,
            "error": result.error,
            "final_screenshot_path": result.final_screenshot_path,
            "subtask_results": [
                self._serialize_subtask_result(subtask_result)
                for subtask_result in result.subtask_results
            ],
        }

        with open(result_path, "w") as f:
            json.dump(result_data, f, indent=2)

        logger.info(f"Detailed result saved to: {result_path}")

    def _serialize_subtask_result(
        self, subtask_result: SubTaskResult
    ) -> Dict[str, Any]:
        """Convert subtask result to serializable format."""
        return {
            "subtask_name": subtask_result.subtask_name,
            "success": subtask_result.success,
            "start_time": subtask_result.start_time.isoformat(),
            "end_time": subtask_result.end_time.isoformat(),
            "duration_seconds": subtask_result.duration_seconds,
            "messages": [
                self._serialize_message(msg) for msg in subtask_result.messages
            ],
            "extracted_output": subtask_result.extracted_output,
            "saved_output_path": subtask_result.saved_output_path,
            "error": subtask_result.error,
        }

    def _serialize_message(self, message: BetaMessageParam) -> Dict[str, Any]:
        """Convert message to serializable format."""
        return {
            "role": message.get("role"),
            "content": (
                str(message.get("content", ""))[:1000] + "..."
                if len(str(message.get("content", ""))) > 1000
                else str(message.get("content", ""))
            ),
        }
