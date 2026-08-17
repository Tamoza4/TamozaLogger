"""
cogs/settings.py — Bot Configuration & Granular Log Routing Slash Commands
===========================================================================
Provides /log commands for guild administrators to configure:
  - Granular log routing per event type (e.g., member_join, voice_move, member_kick, voice_disconnect)
  - Broad category log routing (e.g., members, voice, messages, mod)
  - Ignore list management (channels/roles/users)
  - /log status overview of current configuration
"""

from __future__ import annotations

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from config import LOG_CATEGORIES, LOG_EVENT_TYPES
from database.db import db
from utils.embed_builder import build_embed, Colours

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Settings(commands.Cog, name="Settings"):
    """Configuration commands for TamozaLogger."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Autocomplete for log types / categories
    # ------------------------------------------------------------------

    async def _type_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for granular event types and general categories."""
        guild_id = interaction.guild_id or 0
        lang = "ar"
        if guild_id:
            from database.db import _guild_lang_cache
            lang = _guild_lang_cache.get(guild_id) or "ar"

        choices: list[app_commands.Choice[str]] = []
        for key, info in LOG_EVENT_TYPES.items():
            label = info["name_ar"] if lang == "ar" else info["name_en"]
            # Search against key or label
            if not current or current.lower() in key.lower() or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=key))

        return choices[:25]

    # ------------------------------------------------------------------
    # /log group
    # ------------------------------------------------------------------

    log_group = app_commands.Group(
        name="log",
        description="Configure TamozaLogger log channels and settings.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    # ── /log set ─────────────────────────────────────────────────────────

    @log_group.command(
        name="set",
        description="Set a log channel for a specific event or general category.",
    )
    @app_commands.describe(
        log_type="The specific log event or general category to route.",
        channel="The text channel that will receive these log events.",
    )
    @app_commands.autocomplete(log_type=_type_autocomplete)
    async def log_set(
        self,
        interaction: discord.Interaction,
        log_type: str,
        channel: discord.TextChannel,
    ) -> None:
        """Persist a log channel mapping and confirm to the user."""
        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild(interaction.guild_id)

        clean_type = log_type.strip().lower()
        await db.set_log_channel(interaction.guild_id, clean_type, channel.id)

        lang = await db.get_guild_language(interaction.guild_id)
        type_info = LOG_EVENT_TYPES.get(clean_type)
        type_display = (
            (type_info["name_ar"] if lang == "ar" else type_info["name_en"])
            if type_info else f"`{clean_type}`"
        )

        if lang == "ar":
            title = "✅ تم تعيين روم السجل"
            desc  = f"سيتم الآن إرسال أحداث **{type_display}** إلى {channel.mention}."
            f_type = "نوع السجل"
            f_chan = "الروم"
        else:
            title = "✅ Log Channel Set"
            desc  = f"**{type_display}** events will now be sent to {channel.mention}."
            f_type = "Log Type"
            f_chan = "Channel"

        embed = build_embed(
            event_type="create",
            title=title,
            description=desc,
            colour=Colours.CREATE,
            fields=[
                (f_type, type_display, True),
                (f_chan, f"{channel.mention} (`{channel.id}`)", True),
            ],
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        log.info(
            "Guild %d: set log channel for '%s' to #%s (%d)",
            interaction.guild_id, clean_type, channel.name, channel.id,
        )

    # ── /log remove ──────────────────────────────────────────────────────

    @log_group.command(
        name="remove",
        description="Remove a configured log channel for a specific event or category.",
    )
    @app_commands.describe(
        log_type="The specific log event or category to unbind.",
    )
    @app_commands.autocomplete(log_type=_type_autocomplete)
    async def log_remove(
        self,
        interaction: discord.Interaction,
        log_type: str,
    ) -> None:
        """Remove a log channel mapping."""
        await interaction.response.defer(ephemeral=True)

        clean_type = log_type.strip().lower()
        removed = await db.remove_log_channel(interaction.guild_id, clean_type)

        lang = await db.get_guild_language(interaction.guild_id)
        type_info = LOG_EVENT_TYPES.get(clean_type)
        type_display = (
            (type_info["name_ar"] if lang == "ar" else type_info["name_en"])
            if type_info else f"`{clean_type}`"
        )

        if removed:
            if lang == "ar":
                title = "🗑️ تم إزالة روم السجل"
                desc  = f"تم حذف روم السجل المخصص لـ **{type_display}**."
            else:
                title = "🗑️ Log Channel Removed"
                desc  = f"Log channel configuration for **{type_display}** has been removed."

            embed = build_embed(
                event_type="delete",
                title=title,
                description=desc,
                colour=Colours.DELETE,
            )
        else:
            if lang == "ar":
                title = "⚠️ لم يتم العثور على سجل"
                desc  = f"لا يوجد روم محدد حالياً لـ **{type_display}**."
            else:
                title = "⚠️ Not Configured"
                desc  = f"No log channel was configured for **{type_display}**."

            embed = build_embed(
                event_type="neutral",
                title=title,
                description=desc,
                colour=Colours.UPDATE,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /log clear ───────────────────────────────────────────────────────

    @log_group.command(
        name="clear",
        description="Reset all configured log channels for this server.",
    )
    async def log_clear(self, interaction: discord.Interaction) -> None:
        """Clear all log channels in the guild."""
        await interaction.response.defer(ephemeral=True)

        count = await db.clear_all_log_channels(interaction.guild_id)
        lang  = await db.get_guild_language(interaction.guild_id)

        if lang == "ar":
            title = "🧹 تم إعادة ضبط جميع سجلات الرومات"
            desc  = f"تم حذف **{count}** سجل مخصص. البوت لن يرسل سجلات حتى تعيين رومات جديدة عبر `/log set`."
        else:
            title = "🧹 All Log Channels Cleared"
            desc  = f"Removed **{count}** log channel mapping(s). Use `/log set` to configure new channels."

        embed = build_embed(
            event_type="delete",
            title=title,
            description=desc,
            colour=Colours.DELETE,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /log ignore ──────────────────────────────────────────────────────

    @log_group.command(
        name="ignore",
        description="Add or remove a channel, role, or user from the ignore list.",
    )
    @app_commands.describe(
        action="Add to or remove from the ignore list.",
        entity_type="What kind of entity to ignore.",
        channel="The channel to ignore (if entity_type is 'channel').",
        role="The role to ignore (if entity_type is 'role').",
        user="The user to ignore (if entity_type is 'user').",
    )
    async def log_ignore(
        self,
        interaction: discord.Interaction,
        action: Literal["add", "remove"],
        entity_type: Literal["channel", "role", "user"],
        channel: discord.TextChannel | None = None,
        role: discord.Role | None = None,
        user: discord.Member | None = None,
    ) -> None:
        """Manage the ignore list for this guild."""
        await interaction.response.defer(ephemeral=True)

        entity_map = {"channel": channel, "role": role, "user": user}
        entity = entity_map.get(entity_type)

        if entity is None:
            await interaction.followup.send(
                f"❌ Please provide a **{entity_type}** argument.", ephemeral=True
            )
            return

        await db.ensure_guild(interaction.guild_id)

        if action == "add":
            await db.ignore_add(interaction.guild_id, entity_type, entity.id)
            verb = "added to"
            colour = Colours.UPDATE
        else:
            await db.ignore_remove(interaction.guild_id, entity_type, entity.id)
            verb = "removed from"
            colour = Colours.DELETE

        embed = build_embed(
            event_type="update",
            title="🔇 Ignore List Updated",
            description=f"{entity.mention} has been **{verb}** the ignore list.",
            colour=colour,
            fields=[
                ("Action",      action.capitalize(), True),
                ("Entity Type", entity_type.capitalize(), True),
                ("Target",      f"`{entity.id}`", True),
            ],
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /log status ──────────────────────────────────────────────────────

    @log_group.command(
        name="status",
        description="Show the current logging configuration for this server.",
    )
    async def log_status(self, interaction: discord.Interaction) -> None:
        """Display all active log channel mappings and ignore list size."""
        await interaction.response.defer(ephemeral=True)

        rows     = await db.get_all_log_channels(interaction.guild_id)
        settings = await db.get_guild_settings(interaction.guild_id)
        lang     = await db.get_guild_language(interaction.guild_id)

        if not rows:
            msg = (
                "⚠️ لم يتم ضبط أي رومات للسجلات بعد. استخدم `/log set` للبدء."
                if lang == "ar"
                else "⚠️ No log channels configured yet. Use `/log set` to get started."
            )
            await interaction.followup.send(msg, ephemeral=True)
            return

        specific_lines: list[str] = []
        general_lines:  list[str] = []

        for row in rows:
            cat_key = row["category"]
            ch = interaction.guild.get_channel(row["channel_id"])
            ch_str = ch.mention if ch else f"`{row['channel_id']}` *(deleted?)*"

            info = LOG_EVENT_TYPES.get(cat_key)
            if info:
                name_str = info["name_ar"] if lang == "ar" else info["name_en"]
                if info.get("category") is None:
                    general_lines.append(f"{name_str} → {ch_str}")
                else:
                    specific_lines.append(f"{name_str} → {ch_str}")
            else:
                specific_lines.append(f"`{cat_key}` → {ch_str}")

        fields: list[tuple[str, str, bool]] = []

        if specific_lines:
            f_title = "📌 السجلات المخصصة (Specific Events)" if lang == "ar" else "📌 Specific Event Logs"
            fields.append((f_title, "\n".join(specific_lines), False))

        if general_lines:
            f_title = "📁 السجلات العامة (General Categories)" if lang == "ar" else "📁 General Category Logs"
            fields.append((f_title, "\n".join(general_lines), False))

        if settings:
            ign_ch = len(settings["ignored_channels"])
            ign_ro = len(settings["ignored_roles"])
            ign_us = len(settings["ignored_users"])
            ign_title = "🔇 قائمة الاستثناءات" if lang == "ar" else "🔇 Ignore List"
            ign_desc  = (
                f"الرومات: **{ign_ch}** · الرتب: **{ign_ro}** · الأعضاء: **{ign_us}**"
                if lang == "ar"
                else f"Channels: **{ign_ch}** · Roles: **{ign_ro}** · Users: **{ign_us}**"
            )
            fields.append((ign_title, ign_desc, False))

        embed_title = (
            f"📋 حالة إعدادات السجلات — {interaction.guild.name}"
            if lang == "ar"
            else f"📋 Logging Status — {interaction.guild.name}"
        )

        embed = build_embed(
            event_type="neutral",
            title=embed_title,
            colour=Colours.VOICE,
            fields=fields,
            footer_text="TamozaLogger • /log set | remove | clear",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /language ────────────────────────────────────────────────────────

    @app_commands.command(
        name="language",
        description="Change the bot language for this server (English / العربية).",
    )
    @app_commands.describe(
        language="Choose server language (English 🇬🇧 or Arabic 🇸🇦)."
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="English 🇬🇧", value="en"),
            app_commands.Choice(name="العربية 🇸🇦", value="ar"),
        ]
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def language_command(
        self,
        interaction: discord.Interaction,
        language: app_commands.Choice[str],
    ) -> None:
        await db.set_guild_language(interaction.guild_id, language.value)

        if language.value == "ar":
            title = "✅ تم تغيير لغة البوت"
            desc = "تم ضبط لغة البوت لهذا السيرفر على **العربية 🇸🇦** بنجاح."
        else:
            title = "✅ Bot Language Updated"
            desc = "Server language set to **English 🇬🇧** successfully."

        embed = build_embed(
            event_type="update",
            title=title,
            description=desc,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Helpers: fetch the configured log channel object for a guild + event/category.
# Used by every cog to route embeds to the correct channel.
# ---------------------------------------------------------------------------

async def get_log_channel_obj(
    guild: discord.Guild,
    event_type: str,
    *,
    fallback_category: str | None = None,
) -> discord.TextChannel | None:
    """
    Look up the configured log channel for a specific event_type first.
    If not configured:
      1. Check explicit fallback_category
      2. Check parent category from LOG_EVENT_TYPES dictionary
    Returns the live TextChannel object, or None if not configured.
    """
    clean_event = event_type.strip().lower()

    # 1. Exact event lookup (e.g. "member_join", "voice_move", "voice_disconnect")
    channel_id = await db.get_log_channel(guild.id, clean_event)

    # 2. Explicit fallback category (e.g. "members", "voice", "mod")
    if not channel_id and fallback_category:
        channel_id = await db.get_log_channel(guild.id, fallback_category.strip().lower())

    # 3. Default parent category lookup from LOG_EVENT_TYPES
    if not channel_id and clean_event in LOG_EVENT_TYPES:
        parent_cat = LOG_EVENT_TYPES[clean_event].get("category")
        if parent_cat:
            channel_id = await db.get_log_channel(guild.id, parent_cat)

    if not channel_id:
        return None

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None
    return channel


async def send_log(
    guild: discord.Guild,
    event_type: str,
    *,
    fallback: str | None = None,
    embed: discord.Embed | None = None,
    file: discord.File | None = None,
    embeds: list[discord.Embed] | None = None,
) -> None:
    """
    Route a log embed (and optional file) to the specific or category channel.
    Silently skips if not configured.
    """
    channel = await get_log_channel_obj(guild, event_type, fallback_category=fallback)
    if channel is None:
        return

    kwargs: dict = {}
    if embed:
        kwargs["embed"] = embed
    if embeds:
        kwargs["embeds"] = embeds
    if file:
        kwargs["file"] = file

    try:
        await channel.send(**kwargs)
    except discord.Forbidden:
        log.warning(
            "Cannot send to log channel #%s (%d) in guild %d — missing permissions.",
            channel.name, channel.id, guild.id,
        )
    except discord.HTTPException as exc:
        log.error("Failed to send log to guild %d for %s: %s", guild.id, event_type, exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
