#!/usr/bin/env python3
"""Invoke tasks for syncing financial data to Monarch Money."""

import asyncio

from invoke import Context, task

from monarch_feeder.integration_types import Platform
from monarch_feeder.integrations import INTEGRATIONS
from monarch_feeder.sync import sync_all


@task
def sync(
    ctx: Context,
    platforms: str | None = None,
    dry_run: bool = False,
) -> None:
    """
    Sync all platforms to Monarch Money.

    Args:
        platforms: Comma-separated list of platforms to sync (default: all platforms)
        dry_run: If True, only print what would be done without making changes

    Examples:
        inv sync
        inv sync --platforms human_interest
        inv sync --platforms human_interest,rippling
        inv sync --dry-run
    """
    if platforms is None:
        platform_list = [Platform.HUMAN_INTEREST, Platform.RIPPLING]
    else:
        platform_names = [p.strip() for p in platforms.split(",")]
        platform_list = [Platform(name) for name in platform_names]

    asyncio.run(sync_all(platforms=platform_list, dry_run=dry_run))


@task
def list_integrations(
    ctx: Context,
) -> None:
    """
    List all integrations.
    """
    platforms = [platform.value for platform in INTEGRATIONS]
    print(f"Available platforms: {', '.join(platforms)}")
