"""
utils/permissions_diff.py — Permission Bitfield Diff Engine
============================================================
Computes human-readable diffs between two discord.Permissions or two
discord.PermissionOverwrite objects.  Used by channel_logs and role_logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator

import discord


# ---------------------------------------------------------------------------
# Change types
# ---------------------------------------------------------------------------

class PermChange(Enum):
    ALLOW   = "allow"    # Explicitly granted   (+)
    DENY    = "deny"     # Explicitly denied    (-)
    NEUTRAL = "neutral"  # Reset / no override  (~)
    ADDED   = "added"    # Role perm turned ON
    REMOVED = "removed"  # Role perm turned OFF


# Permissions considered "sensitive" — highlighted with a warning
SENSITIVE_PERMISSIONS: frozenset[str] = frozenset({
    "administrator",
    "ban_members",
    "kick_members",
    "manage_guild",
    "manage_channels",
    "manage_roles",
    "manage_permissions",
    "manage_webhooks",
    "manage_messages",
    "mention_everyone",
    "view_audit_log",
    "manage_nicknames",
    "moderate_members",
})


@dataclass(frozen=True)
class PermDiffEntry:
    name: str
    change: PermChange
    is_sensitive: bool

    @property
    def symbol(self) -> str:
        mapping = {
            PermChange.ALLOW:   "✅",
            PermChange.DENY:    "❌",
            PermChange.NEUTRAL: "⬜",
            PermChange.ADDED:   "🟢",
            PermChange.REMOVED: "🔴",
        }
        return mapping[self.change]

    @property
    def display_name(self) -> str:
        name = self.name.replace("_", " ").title()
        if self.is_sensitive:
            return f"⚠️ {name}"
        return name

    def __str__(self) -> str:
        return f"{self.symbol} {self.display_name}"


# ---------------------------------------------------------------------------
# Overwrite diff (channel permission overwrites for a role/member)
# ---------------------------------------------------------------------------

def diff_overwrites(
    before: discord.PermissionOverwrite,
    after: discord.PermissionOverwrite,
) -> list[PermDiffEntry]:
    """
    Compute the diff between two ``discord.PermissionOverwrite`` objects.

    Returns a list of ``PermDiffEntry`` items where the value changed.
    """
    results: list[PermDiffEntry] = []

    before_dict = dict(before)
    after_dict  = dict(after)

    all_perms = set(before_dict) | set(after_dict)

    for perm_name in sorted(all_perms):
        b_val = before_dict.get(perm_name)
        a_val = after_dict.get(perm_name)

        if b_val == a_val:
            continue  # No change

        if a_val is True:
            change = PermChange.ALLOW
        elif a_val is False:
            change = PermChange.DENY
        else:
            change = PermChange.NEUTRAL  # Reset to default (None)

        results.append(
            PermDiffEntry(
                name=perm_name,
                change=change,
                is_sensitive=perm_name in SENSITIVE_PERMISSIONS,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Permission diff (role permissions — boolean True/False only)
# ---------------------------------------------------------------------------

def diff_permissions(
    before: discord.Permissions,
    after: discord.Permissions,
) -> list[PermDiffEntry]:
    """
    Compute the diff between two ``discord.Permissions`` objects.

    Returns a list of ``PermDiffEntry`` items where the value changed.
    """
    results: list[PermDiffEntry] = []

    before_dict = dict(before)
    after_dict  = dict(after)

    for perm_name in sorted(set(before_dict) | set(after_dict)):
        b_val = before_dict.get(perm_name, False)
        a_val = after_dict.get(perm_name, False)

        if b_val == a_val:
            continue

        change = PermChange.ADDED if a_val else PermChange.REMOVED
        results.append(
            PermDiffEntry(
                name=perm_name,
                change=change,
                is_sensitive=perm_name in SENSITIVE_PERMISSIONS,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_perm_diff(entries: list[PermDiffEntry], max_items: int = 20) -> str:
    """
    Format a list of ``PermDiffEntry`` items into a displayable string.

    Parameters
    ----------
    entries:
        The diff entries to format.
    max_items:
        Truncate to this many entries to avoid hitting Discord's 1024-char
        field value limit.

    Returns
    -------
    str
        Newline-separated list of formatted entries, or "(No changes)" if empty.
    """
    if not entries:
        return "*(No permission changes)*"

    lines = [str(e) for e in entries[:max_items]]
    if len(entries) > max_items:
        lines.append(f"*… and {len(entries) - max_items} more*")

    return "\n".join(lines)


def format_overwrite_diff(
    before: discord.PermissionOverwrite,
    after: discord.PermissionOverwrite,
) -> str:
    """Compute and format an overwrite diff in one step."""
    return format_perm_diff(diff_overwrites(before, after))


def format_permission_diff(
    before: discord.Permissions,
    after: discord.Permissions,
) -> str:
    """Compute and format a role permission diff in one step."""
    return format_perm_diff(diff_permissions(before, after))


def full_permissions_list(perms: discord.Permissions) -> str:
    """
    Render all *enabled* permissions for a role as a formatted code block.
    Used when logging a deleted role so its permissions can be recovered.
    """
    enabled = [
        name.replace("_", " ").title()
        for name, value in perms
        if value
    ]
    if not enabled:
        return "*(No permissions)*"
    return "```\n" + "\n".join(enabled) + "\n```"
