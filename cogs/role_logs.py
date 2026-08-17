"""
cogs/role_logs.py — Role & Permission Event Logger
===================================================
Handles:
  - on_guild_role_create     Executor attribution
  - on_guild_role_delete     Full permission backup in code block
  - on_guild_role_update     Name, color, hoist, mentionable, icon,
                             granular permission bitfield diff with
                             sensitive permission highlighting
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.settings import send_log
from database.db import db
from utils.audit_matcher import fetch_audit_log_entry, format_actor
from utils.embed_builder import build_embed, role_embed, Colours
from utils.i18n import t
from utils.permissions_diff import (
    diff_permissions,
    format_perm_diff,
    format_permission_diff,
    full_permissions_list,
    SENSITIVE_PERMISSIONS,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _colour_str(colour: discord.Colour) -> str:
    if colour.value == 0:
        return "`Default (no colour)`"
    return f"`#{colour.value:06X}` 🎨"


def _colour_swatch(colour: discord.Colour) -> int | None:
    """Return the colour int if non-default, else None."""
    return colour.value if colour.value != 0 else None


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class RoleLogs(commands.Cog, name="RoleLogs"):
    """Logs all role lifecycle and permission change events."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # on_guild_role_create
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        guild = role.guild
        lang  = await db.get_guild_language(guild.id)

        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.role_create,
            target_id=role.id,
        )
        yes_no = ("نعم" if role.hoist else "لا") if lang == "ar" else ("Yes" if role.hoist else "No")
        ment_yes_no = ("نعم" if role.mentionable else "لا") if lang == "ar" else ("Yes" if role.mentionable else "No")

        fields: list[tuple[str, str, bool]] = [
            (t("name", lang),        role.mention + f" (`{role.name}`)", True),
            (t("created_by", lang),  format_actor(executor), True),
            (t("colour", lang),      _colour_str(role.colour), True),
            (t("hoisted", lang),     yes_no, True),
            (t("mentionable", lang), ment_yes_no, True),
            (t("position", lang),    str(role.position), True),
            (t("role_id", lang),     f"`{role.id}`", True),
        ]
        if reason:
            fields.append((t("reason", lang), reason, False))

        embed = build_embed(
            event_type="create",
            title=t("role_created", lang),
            colour=_colour_swatch(role.colour) or Colours.CREATE,
            fields=fields,
        )
        await send_log(guild, "role_create", fallback="roles", embed=embed)

    # ------------------------------------------------------------------
    # on_guild_role_delete
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        guild = role.guild
        lang  = await db.get_guild_language(guild.id)

        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.role_delete,
            target_id=role.id,
        )

        perms_backup = full_permissions_list(role.permissions)
        yes_no = ("نعم" if role.hoist else "لا") if lang == "ar" else ("Yes" if role.hoist else "No")
        ment_yes_no = ("نعم" if role.mentionable else "لا") if lang == "ar" else ("Yes" if role.mentionable else "No")

        fields: list[tuple[str, str, bool]] = [
            (t("name", lang),        f"`{role.name}`", True),
            (t("deleted_by", lang),  format_actor(executor), True),
            (t("colour", lang),      _colour_str(role.colour), True),
            (t("hoisted", lang),     yes_no, True),
            (t("mentionable", lang), ment_yes_no, True),
            (t("role_id", lang),     f"`{role.id}`", True),
            (t("perms_backup", lang),perms_backup, False),
        ]
        if reason:
            fields.append((t("reason", lang), reason, False))

        embed = build_embed(
            event_type="delete",
            title=t("role_deleted", lang),
            colour=Colours.DELETE,
            fields=fields,
        )
        await send_log(guild, "role_delete", fallback="roles", embed=embed)

    # ------------------------------------------------------------------
    # on_guild_role_update
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> None:
        guild = after.guild
        lang  = await db.get_guild_language(guild.id)
        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.role_update,
            target_id=after.id,
        )

        changes: list[tuple[str, str, bool]] = []

        # Name
        if before.name != after.name:
            changes.append((t("name", lang), f"`{before.name}` → `{after.name}`", False))

        # Colour
        if before.colour != after.colour:
            changes.append((
                t("colour", lang),
                f"{_colour_str(before.colour)} → {_colour_str(after.colour)}",
                True,
            ))

        # Hoist
        if before.hoist != after.hoist:
            changes.append((
                t("hoisted", lang),
                f"`{before.hoist}` → `{after.hoist}`",
                True,
            ))

        # Mentionable
        if before.mentionable != after.mentionable:
            changes.append((
                t("mentionable", lang),
                f"`{before.mentionable}` → `{after.mentionable}`",
                True,
            ))

        # Icon
        if before.icon != after.icon:
            changes.append(("Icon" if lang == "en" else "الأيقونة", "Changed" if lang == "en" else "تم التغيير", True))

        # Unicode emoji
        if before.unicode_emoji != after.unicode_emoji:
            changes.append((
                "Emoji" if lang == "en" else "الإيموجي",
                f"`{before.unicode_emoji}` → `{after.unicode_emoji}`",
                True,
            ))

        # Permission bitfield diff
        if before.permissions != after.permissions:
            diff_entries = diff_permissions(before.permissions, after.permissions)
            diff_text    = format_perm_diff(diff_entries)

            # Check for sensitive permissions
            sensitive_changed = [
                e for e in diff_entries if e.is_sensitive
            ]
            if sensitive_changed:
                sensitive_text = "\n".join(str(e) for e in sensitive_changed)
                changes.append((
                    t("sensitive_perms", lang),
                    sensitive_text,
                    False,
                ))

            changes.append((t("perm_changes", lang), diff_text, False))

        if not changes:
            return

        changes.insert(0, (
            "Role" if lang == "en" else "الرتبة",
            after.mention + f" (`{after.id}`)",
            True,
        ))
        if executor:
            changes.insert(1, (t("updated_by", lang), format_actor(executor), True))
        if reason:
            changes.append((t("reason", lang), reason, False))

        embed = build_embed(
            event_type="update",
            title=t("role_updated", lang),
            colour=_colour_swatch(after.colour) or Colours.UPDATE,
            fields=changes,
            footer_text=f"Role ID: {after.id} • TamozaLogger",
        )
        await send_log(guild, "role_update", fallback="roles", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleLogs(bot))
