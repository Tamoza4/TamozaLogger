"""
utils/audit_matcher.py — Delayed Audit Log Fetcher
===================================================
Discord's Audit Log has inherent API propagation latency.  Querying it
immediately after an event often returns stale data.  This module
implements a robust async helper that:

  1. Waits a configurable delay (default 0.75 s) before querying.
  2. Fetches the N most recent entries for the given action.
  3. Matches entries against the target within a recency window.
  4. Returns (executor, reason) or (None, None) on no match.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import discord

from config import AUDIT_LOG_DELAY, AUDIT_LOG_LIMIT, AUDIT_LOG_WINDOW

log = logging.getLogger(__name__)


async def fetch_audit_log_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    *,
    target_id: int | None = None,
    delay: float = AUDIT_LOG_DELAY,
    window: float = AUDIT_LOG_WINDOW,
    limit: int = AUDIT_LOG_LIMIT,
) -> tuple[discord.User | discord.Member | None, str | None]:
    """
    Fetch the most relevant Audit Log entry for a given action.

    Parameters
    ----------
    guild:
        The guild whose audit log to query.
    action:
        The ``discord.AuditLogAction`` to filter by.
    target_id:
        The Discord ID of the object that was acted upon.
        When provided, entries are filtered to only match this target.
        Pass ``None`` to skip target filtering (e.g., for guild updates).
    delay:
        Seconds to wait before querying (allows audit log to propagate).
    window:
        Maximum age (in seconds) of an audit log entry to be considered a match.
    limit:
        Number of entries to fetch per API call.

    Returns
    -------
    tuple[executor, reason]
        ``executor`` is the ``discord.User`` / ``discord.Member`` who performed
        the action, or ``None`` if the bot lacks ``view_audit_log`` permission or
        no matching entry was found within the recency window.
        ``reason`` is the audit log reason string, or ``None``.
    """
    # Respect the propagation delay
    if delay > 0:
        await asyncio.sleep(delay)

    # Guard: ensure the bot has audit log access
    me = guild.me
    if me is None or not guild.me.guild_permissions.view_audit_log:
        log.debug("Missing VIEW_AUDIT_LOG permission in guild %s", guild.id)
        return None, None

    now = datetime.now(tz=timezone.utc)

    try:
        async for entry in guild.audit_logs(limit=limit, action=action):
            # Recency check — entry must be within the time window
            age = (now - entry.created_at.replace(tzinfo=timezone.utc)).total_seconds()
            if age > window:
                # Entries are ordered newest-first; no point continuing
                break

            # Target check — skip if the entry targets a different object
            if target_id is not None:
                entry_target_id = getattr(entry.target, "id", None)
                if entry_target_id != target_id:
                    continue

            return entry.user, entry.reason

    except discord.Forbidden:
        log.warning("Forbidden: cannot read audit log in guild %s (%d)", guild.name, guild.id)
    except discord.HTTPException as exc:
        log.error("HTTP error reading audit log in guild %d: %s", guild.id, exc)

    return None, None


def format_actor(
    executor: discord.User | discord.Member | None,
    *,
    fallback: str = "Unknown",
) -> str:
    """Return a clickable mention + tag + ID string for audit log executor."""
    if executor is None:
        return fallback
    return f"{executor.mention} · {executor} · `{executor.id}`"
