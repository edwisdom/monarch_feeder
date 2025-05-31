#!/usr/bin/env python3
"""
Invoke tasks for computer use automation.
Replaces shell scripts with a clean, extensible Python interface.
"""

from pathlib import Path

from invoke import Context, task

from monarch_feeder.computer_use_demo.automation_orchestrator import AutomationType

# Shared container configuration
CONTAINER_IMAGE = "computer-use-automation"
CONTAINER_NAME_PREFIX = "automation"
DOCKERFILE = "monarch_feeder/computer_use_demo/Dockerfile"

# Default output directories
DEFAULT_OUTPUT_DIR = "automation_outputs"
DEFAULT_SCREENSHOT_DIR = "automation_screenshots"

# Available automations (corresponds to AutomationType enum values)
AVAILABLE_AUTOMATIONS = [automation.value for automation in AutomationType]


def ensure_env_file(ctx: Context) -> None:
    """Ensure .env file exists."""
    if not Path(".env").exists():
        print("❌ Error: .env file not found!")
        print("📝 Please create a .env file with your credentials.")
        if Path("env.example").exists():
            print("💡 You can copy env.example to .env and fill in your values:")
            print("   cp env.example .env")
        raise SystemExit(1)


def ensure_output_dirs() -> None:
    """Ensure output directories exist."""
    Path(DEFAULT_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(DEFAULT_SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)


def image_exists(ctx: Context, image_name: str) -> bool:
    """Check if Docker image exists."""
    result = ctx.run(f"docker image inspect {image_name}", hide=True, warn=True)
    return result.ok


def container_exists(ctx: Context, container_name: str) -> bool:
    """Check if container exists."""
    result = ctx.run(
        f'docker ps -a --format "table {{{{.Names}}}}" | grep -q "^{container_name}$"',
        hide=True,
        warn=True,
    )
    return result.ok


def validate_automations(automations: list[str]) -> None:
    """Validate that all automation names are supported."""
    invalid = [name for name in automations if name not in AVAILABLE_AUTOMATIONS]
    if invalid:
        available = ", ".join(AVAILABLE_AUTOMATIONS)
        invalid_str = ", ".join(invalid)
        print(f"❌ Unknown automation(s): {invalid_str}")
        print(f"💡 Available automations: {available}")
        raise SystemExit(1)


@task
def build(ctx: Context) -> None:
    """Build the shared computer use automation container."""
    print(f"🏗️  Building shared computer use automation container...")

    ctx.run(
        f"docker build -f {DOCKERFILE} -t {CONTAINER_IMAGE} .",
        pty=True,
    )

    print("✅ Build completed successfully!")
    print("🚀 To run: inv run --automations <automation_names>")


@task
def clean(ctx: Context, images: bool = False) -> None:
    """Clean up containers and optionally images."""
    print("🔄 Cleaning all automation containers...")
    result = ctx.run(
        f'docker ps -a --format "{{{{.Names}}}}" | grep "^{CONTAINER_NAME_PREFIX}-"',
        hide=True,
        warn=True,
    )
    if result.ok and result.stdout.strip():
        containers = result.stdout.strip().split("\n")
        for container in containers:
            ctx.run(f"docker stop {container}", hide=True, warn=True)
            ctx.run(f"docker rm {container}", hide=True, warn=True)

    # Remove image if requested
    if images and image_exists(ctx, CONTAINER_IMAGE):
        print(f"🗑️  Removing image: {CONTAINER_IMAGE}")
        ctx.run(f"docker rmi {CONTAINER_IMAGE}", warn=True)


@task
def run(
    ctx: Context, automations: str = "human_interest", build_if_missing: bool = True
) -> None:
    """Run automation(s). Pass comma-separated automation names."""
    # Parse automation list
    automation_list = [name.strip() for name in automations.split(",")]
    validate_automations(automation_list)

    container_name = f"{CONTAINER_NAME_PREFIX}-{'-'.join(automation_list)}"

    # Validate environment
    ensure_env_file(ctx)
    ensure_output_dirs()

    # Build image if it doesn't exist
    if not image_exists(ctx, CONTAINER_IMAGE):
        if build_if_missing:
            print(f"🏗️  Image not found. Building {CONTAINER_IMAGE}...")
            build(ctx)
        else:
            print(f"❌ Image {CONTAINER_IMAGE} not found!")
            print("💡 Run: inv build")
            raise SystemExit(1)

    # Clean up any existing container for this combination
    if container_exists(ctx, container_name):
        print(f"🔄 Stopping existing container: {container_name}")
        ctx.run(f"docker stop {container_name}", hide=True, warn=True)
        ctx.run(f"docker rm {container_name}", hide=True, warn=True)

    print(f"🚀 Running automation(s): {', '.join(automation_list)}")
    print("📊 This will extract your data")
    print("⏱️  This may take several minutes to complete")
    print()

    # Run the container using the entrypoint script with auto-exit enabled
    ctx.run(
        f"docker run --rm --name {container_name} "
        f"--env-file .env "
        f"-e AUTO_EXIT=true "
        f"-e AUTOMATION_LIST={','.join(automation_list)} "
        f"-v $(pwd)/{DEFAULT_OUTPUT_DIR}:/home/computeruse/{DEFAULT_OUTPUT_DIR} "
        f"-v $(pwd)/{DEFAULT_SCREENSHOT_DIR}:/home/computeruse/{DEFAULT_SCREENSHOT_DIR} "
        f"{CONTAINER_IMAGE}",
        pty=True,
    )

    print()
    print("✅ Automation completed!")
    print("📁 Results saved to automation-specific directories:")
    for automation in automation_list:
        print(f"   - {DEFAULT_OUTPUT_DIR}/{automation}/ (JSON data)")
        print(f"   - {DEFAULT_SCREENSHOT_DIR}/{automation}/ (screenshots)")


@task
def list_automations(ctx: Context) -> None:
    """List available automations."""
    print("Available automations:")
    for name in AVAILABLE_AUTOMATIONS:
        print(f"  • {name}")
    print()
    print("Usage: inv run --automations <automation1,automation2,...>")
    print("Example: inv run --automations human_interest")


@task
def shell(ctx: Context) -> None:
    """Start a shell in the automation container for debugging."""
    container_name = f"{CONTAINER_NAME_PREFIX}-shell"

    if not image_exists(ctx, CONTAINER_IMAGE):
        print(f"❌ Image {CONTAINER_IMAGE} not found!")
        print("💡 Run: inv build")
        raise SystemExit(1)

    ensure_env_file(ctx)
    ensure_output_dirs()

    print(f"🐚 Starting shell in automation container...")

    ctx.run(
        f"docker run --rm -it --name {container_name} "
        f"--env-file .env "
        f"-v $(pwd)/{DEFAULT_OUTPUT_DIR}:/home/computeruse/{DEFAULT_OUTPUT_DIR} "
        f"-v $(pwd)/{DEFAULT_SCREENSHOT_DIR}:/home/computeruse/{DEFAULT_SCREENSHOT_DIR} "
        f"--entrypoint bash "
        f"{CONTAINER_IMAGE}",
        pty=True,
    )


# Convenience aliases
@task
def build_and_run_all(ctx: Context) -> None:
    """Build and run all automations (convenience alias)."""
    build(ctx)
    run(ctx, AVAILABLE_AUTOMATIONS.join(","))
