"""
cogs/channel_logs.py — Channel, Category & Thread Event Logger
===============================================================
Handles:
  - on_guild_channel_create / delete / update
    Name, type, category, topic, slowmode, NSFW, bitrate changes.
    Full permission overwrite diff per target (role/member).
  - on_thread_create / delete / update
    Archive, lock, tags, slowmode changes.
"""

from __future__ import annotations

import logging
from typing import Union

import discord
from discord.ext import commands

from cogs.settings import send_log
from database.db import db
from utils.audit_matcher import fetch_audit_log_entry, format_actor
from utils.embed_builder import build_embed, fmt_channel, Colours
from utils.i18n import t
from utils.permissions_diff import (
    diff_overwrites,
    format_perm_diff,
    format_overwrite_diff,
)

log = logging.getLogger(__name__)

GuildChannel = Union[
    discord.TextChannel,
    discord.VoiceChannel,
    discord.CategoryChannel,
    discord.StageChannel,
    discord.ForumChannel,
    discord.abc.GuildChannel,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _channel_type_str(channel: GuildChannel) -> str:
    type_map = {
        discord.ChannelType.text:          "📝 Text",
        discord.ChannelType.voice:         "🔊 Voice",
        discord.ChannelType.category:      "📁 Category",
        discord.ChannelType.stage_voice:   "🎤 Stage",
        discord.ChannelType.forum:         "🗂️ Forum",
        discord.ChannelType.news:          "📢 Announcement",
        discord.ChannelType.private_thread:"🧵 Private Thread",
        discord.ChannelType.public_thread: "🧵 Public Thread",
        discord.ChannelType.news_thread:   "🧵 News Thread",
    }
    return type_map.get(channel.type, str(channel.type))


def _slowmode_str(seconds: int) -> str:
    if seconds == 0:
        return "Off"
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ChannelLogs(commands.Cog, name="ChannelLogs"):
    """Logs channel, category, and thread lifecycle events."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Channel Create
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: GuildChannel) -> None:
        guild = channel.guild
        lang  = await db.get_guild_language(guild.id)

        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.channel_create,
            target_id=channel.id,
        )
        cat_name = channel.category.name if channel.category else ("لا يوجد" if lang == "ar" else "None")
        fields: list[tuple[str, str, bool]] = [
            (t("name", lang),       f"`{channel.name}`", True),
            (t("type", lang),       _channel_type_str(channel), True),
            (t("category", lang),   cat_name, True),
            (t("created_by", lang), format_actor(executor), True),
            (t("channel_id", lang), f"`{channel.id}`", True),
        ]
        if reason:
            fields.append((t("reason", lang), reason, False))

        embed = build_embed(
            event_type="create",
            title=t("channel_created", lang),
            description=channel.mention,
            fields=fields,
        )
        await send_log(guild, "channel_create", fallback="channels", embed=embed)

    # ------------------------------------------------------------------
    # Channel Delete
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel) -> None:
        guild = channel.guild
        lang  = await db.get_guild_language(guild.id)

        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.channel_delete,
            target_id=channel.id,
        )
        cat_name = channel.category.name if channel.category else ("لا يوجد" if lang == "ar" else "None")
        fields: list[tuple[str, str, bool]] = [
            (t("name", lang),       f"`{channel.name}`", True),
            (t("type", lang),       _channel_type_str(channel), True),
            (t("category", lang),   cat_name, True),
            (t("deleted_by", lang), format_actor(executor), True),
            (t("channel_id", lang), f"`{channel.id}`", True),
        ]
        if reason:
            fields.append((t("reason", lang), reason, False))

        embed = build_embed(
            event_type="delete",
            title=t("channel_deleted", lang),
            description=f"`#{channel.name}`",
            fields=fields,
        )
        await send_log(guild, "channel_delete", fallback="channels", embed=embed)

    # ------------------------------------------------------------------
    # Channel Update
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: GuildChannel, after: GuildChannel
    ) -> None:
        guild = after.guild
        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.channel_update,
            target_id=after.id,
        )

        changes: list[tuple[str, str, bool]] = []

        # Name
        if before.name != after.name:
            changes.append(("Name", f"`{before.name}` → `{after.name}`", False))

        # Topic (TextChannel / ForumChannel)
        b_topic = getattr(before, "topic", None)
        a_topic = getattr(after, "topic", None)
        if b_topic != a_topic:
            changes.append((
                "Topic",
                f"**Before:** {b_topic or '*None*'}\n**After:** {a_topic or '*None*'}",
                False,
            ))

        # Slowmode
        b_slow = getattr(before, "slowmode_delay", None)
        a_slow = getattr(after,  "slowmode_delay", None)
        if b_slow != a_slow and b_slow is not None and a_slow is not None:
            changes.append(("Slowmode", f"`{_slowmode_str(b_slow)}` → `{_slowmode_str(a_slow)}`", True))

        # NSFW
        b_nsfw = getattr(before, "nsfw", None)
        a_nsfw = getattr(after,  "nsfw", None)
        if b_nsfw != a_nsfw and b_nsfw is not None:
            changes.append(("NSFW", f"`{b_nsfw}` → `{a_nsfw}`", True))

        # Bitrate (VoiceChannel)
        b_br = getattr(before, "bitrate", None)
        a_br = getattr(after,  "bitrate", None)
        if b_br != a_br and b_br is not None:
            changes.append(("Bitrate", f"`{b_br // 1000}kbps` → `{a_br // 1000}kbps`", True))

        # Category
        if before.category != after.category:
            changes.append((
                "Category",
                f"`{before.category.name if before.category else 'None'}` → "
                f"`{after.category.name if after.category else 'None'}`",
                True,
            ))

        # Permission overwrites diff
        await self._check_overwrite_diff(guild, before, after, executor)

        if not changes:
            return  # Nothing interesting changed

        changes.insert(0, ("Channel", after.mention + f" (`{after.id}`)", True))
        if executor:
            changes.insert(1, ("Updated By", format_actor(executor), True))
        if reason:
            changes.append(("Reason", reason, False))

        embed = build_embed(
            event_type="update",
            title="✏️ Channel Updated",
            fields=changes,
        )
        await send_log(guild, "channel_update", fallback="channels", embed=embed)

    async def _check_overwrite_diff(
        self,
        guild: discord.Guild,
        before: GuildChannel,
        after: GuildChannel,
        executor: discord.User | discord.Member | None,
    ) -> None:
        """Detect and log permission overwrite changes for a channel."""
        before_ow = dict(before.overwrites)
        after_ow  = dict(after.overwrites)
        all_targets = set(before_ow) | set(after_ow)

        for target in all_targets:
            b_ow = before_ow.get(target, discord.PermissionOverwrite())
            a_ow = after_ow.get(target,  discord.PermissionOverwrite())

            entries = diff_overwrites(b_ow, a_ow)
            if not entries:
                continue

            diff_text = format_perm_diff(entries)
            target_name = getattr(target, "name", str(target))
            target_type = "Role" if isinstance(target, discord.Role) else "Member"

            fields: list[tuple[str, str, bool]] = [
                ("Channel",    after.mention + f" (`{after.id}`)", True),
                ("Target",     f"{target_name} (`{target.id}`)", True),
                ("Type",       target_type, True),
                ("Updated By", format_actor(executor), True),
                ("Changes",    diff_text, False),
            ]

            embed = build_embed(
                event_type="update",
                title="🔐 Permission Overwrite Changed",
                fields=fields,
            )
            await send_log(guild, "channel_update", fallback="channels", embed=embed)

    # ------------------------------------------------------------------
    # Thread Create
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        guild = thread.guild
        owner = thread.owner
        fields: list[tuple[str, str, bool]] = [
            ("Name",      f"`{thread.name}`", True),
            ("Parent",    thread.parent.mention if thread.parent else "N/A", True),
            ("Created By",f"{owner.mention if owner else 'Unknown'} (`{thread.owner_id}`)", True),
            ("Archived",  str(thread.archived), True),
            ("Locked",    str(thread.locked),   True),
            ("Auto-Archive", f"{thread.auto_archive_duration}m", True),
            ("Thread ID", f"`{thread.id}`", True),
        ]
        embed = build_embed(
            event_type="create",
            title="🧵 Thread Created",
            description=thread.mention,
            fields=fields,
        )
        await send_log(guild, "channel_create", fallback="channels", embed=embed)

    # ------------------------------------------------------------------
    # Thread Delete
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        guild = thread.guild
        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.thread_delete,
            target_id=thread.id,
        )
        fields: list[tuple[str, str, bool]] = [
            ("Name",       f"`{thread.name}`", True),
            ("Parent",     thread.parent.mention if thread.parent else "N/A", True),
            ("Deleted By", format_actor(executor), True),
            ("Thread ID",  f"`{thread.id}`", True),
        ]
        if reason:
            fields.append(("Reason", reason, False))
        embed = build_embed(
            event_type="delete",
            title="🧵 Thread Deleted",
            description=f"`{thread.name}`",
            fields=fields,
        )
        await send_log(guild, "channel_delete", fallback="channels", embed=embed)

    # ------------------------------------------------------------------
    # Thread Update
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_thread_update(
        self, before: discord.Thread, after: discord.Thread
    ) -> None:
        guild = after.guild
        changes: list[tuple[str, str, bool]] = []

        if before.name != after.name:
            changes.append(("Name", f"`{before.name}` → `{after.name}`", False))
        if before.archived != after.archived:
            changes.append(("Archived", f"`{before.archived}` → `{after.archived}`", True))
        if before.locked != after.locked:
            changes.append(("Locked", f"`{before.locked}` → `{after.locked}`", True))
        if before.slowmode_delay != after.slowmode_delay:
            changes.append((
                "Slowmode",
                f"`{_slowmode_str(before.slowmode_delay)}` → `{_slowmode_str(after.slowmode_delay)}`",
                True,
            ))

        # Applied tags (Forum threads)
        if hasattr(before, "applied_tags") and before.applied_tags != after.applied_tags:
            b_tags = {t.name for t in before.applied_tags}
            a_tags = {t.name for t in after.applied_tags}
            added   = a_tags - b_tags
            removed = b_tags - a_tags
            if added:
                changes.append(("Tags Added",   ", ".join(f"`{t}`" for t in added),   True))
            if removed:
                changes.append(("Tags Removed", ", ".join(f"`{t}`" for t in removed), True))

        if not changes:
            return

        changes.insert(0, ("Thread", after.mention + f" (`{after.id}`)", True))

        embed = build_embed(
            event_type="update",
            title="🧵 Thread Updated",
            fields=changes,
        )
        await send_log(guild, "channel_update", fallback="channels", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChannelLogs(bot))
