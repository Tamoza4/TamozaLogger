"""
cogs/server_logs.py — Server & Moderation Event Logger
=======================================================
Handles:
  - on_member_ban / on_member_unban    Mod attribution + reason
  - on_automod_action_execution        Rule name, keyword, action, channel, user
  - on_guild_update                    Name, icon, banner, verification, system channel
  - on_webhooks_update                 Webhook create / delete / update
  - on_guild_emojis_update             Emoji additions and deletions
  - on_guild_stickers_update           Sticker additions and deletions
  - on_audit_log_entry_create          Soundboard changes (via audit log)
"""

from __future__ import annotations

import logging
from typing import Union

import discord
from discord.ext import commands

from cogs.settings import send_log
from database.db import db
from utils.audit_matcher import fetch_audit_log_entry, format_actor
from utils.embed_builder import build_embed, fmt_user, Colours
from utils.i18n import t

log = logging.getLogger(__name__)

# Map AutoMod rule action types to human-readable strings
_AUTOMOD_ACTION_MAP = {
    discord.AutoModRuleActionType.block_message:    "🚫 Message Blocked",
    discord.AutoModRuleActionType.send_alert_message: "📢 Alert Sent",
    discord.AutoModRuleActionType.timeout:          "⏱️ Timeout Applied",
}

_VERIFICATION_LEVELS = {
    discord.VerificationLevel.none:     "None",
    discord.VerificationLevel.low:      "Low (verified email)",
    discord.VerificationLevel.medium:   "Medium (5 min Discord account)",
    discord.VerificationLevel.high:     "High (10 min server member)",
    discord.VerificationLevel.highest:  "Highest (verified phone)",
}


class ServerLogs(commands.Cog, name="ServerLogs"):
    """Logs server-level events, moderation actions, and integrations."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Bans
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: discord.User | discord.Member
    ) -> None:
        lang = await db.get_guild_language(guild.id)
        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.ban,
            target_id=user.id,
        )
        fields: list[tuple[str, str, bool]] = [
            (t("user", lang),      fmt_user(user), True),
            (t("banned_by", lang), format_actor(executor), True),
            (t("reason", lang),    reason or t("no_reason", lang), False),
            (t("user_id", lang),   f"`{user.id}`", True),
        ]
        embed = build_embed(
            event_type="ban",
            title=t("member_banned_title", lang),
            colour=Colours.DELETE,
            fields=fields,
            author_name=str(user),
            author_icon_url=user.display_avatar.url,
            thumbnail_url=user.display_avatar.url,
        )
        await send_log(guild, "member_ban", fallback="mod", embed=embed)

    # ------------------------------------------------------------------
    # Unbans
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_unban(
        self, guild: discord.Guild, user: discord.User
    ) -> None:
        lang = await db.get_guild_language(guild.id)
        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.unban,
            target_id=user.id,
        )
        fields: list[tuple[str, str, bool]] = [
            (t("user", lang),        fmt_user(user), True),
            (t("unbanned_by", lang),  format_actor(executor), True),
            (t("reason", lang),      reason or t("no_reason", lang), False),
            (t("user_id", lang),     f"`{user.id}`", True),
        ]
        embed = build_embed(
            event_type="unban",
            title=t("member_unbanned_title", lang),
            colour=Colours.CREATE,
            fields=fields,
            author_name=str(user),
            author_icon_url=user.display_avatar.url,
            thumbnail_url=user.display_avatar.url,
        )
        await send_log(guild, "member_ban", fallback="mod", embed=embed)

    # ------------------------------------------------------------------
    # AutoMod
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_automod_action_execution(
        self, execution: discord.AutoModActionExecution
    ) -> None:
        guild = self.bot.get_guild(execution.guild_id)
        if guild is None:
            return

        lang   = await db.get_guild_language(guild.id)
        member = guild.get_member(execution.user_id)
        action_type = getattr(execution.action, "type", None)

        if lang == "ar":
            ar_act_map = {
                discord.AutoModRuleActionType.block_message: "🚫 منع الرسالة",
                discord.AutoModRuleActionType.send_alert_message: "📢 إرسال تنبيه",
                discord.AutoModRuleActionType.timeout: "⏱️ تطبيق تايم آوت",
            }
            action_str = ar_act_map.get(action_type, str(action_type))
        else:
            action_str = _AUTOMOD_ACTION_MAP.get(action_type, str(action_type))

        fields: list[tuple[str, str, bool]] = [
            (t("user", lang),            fmt_user(member) if member else f"`{execution.user_id}`", True),
            (t("action", lang),          action_str, True),
            (t("rule", lang),            f"`{execution.rule_id}`", True),
            (t("channel", lang),         f"<#{execution.channel_id}>" if execution.channel_id else "N/A", True),
            (t("matched_content", lang), f"```\n{execution.matched_content or 'N/A'}\n```" if execution.matched_content else "N/A", False),
            (t("matched_keyword", lang), f"`{execution.matched_keyword}`" if execution.matched_keyword else "N/A", True),
        ]

        if (
            action_type == discord.AutoModRuleActionType.timeout
            and execution.action.metadata
        ):
            dur = getattr(execution.action.metadata, "duration", None)
            if dur:
                dur_label = "مدة التايم آوت" if lang == "ar" else "Timeout Duration"
                fields.append((dur_label, str(dur), True))

        embed = build_embed(
            event_type="mod",
            title=t("automod_action_title", lang),
            colour=Colours.MOD,
            fields=fields,
            author_name=str(member) if member else f"User {execution.user_id}",
            author_icon_url=(member.display_avatar.url if member else None),
        )
        await send_log(guild, "automod", fallback="mod", embed=embed)

    # ------------------------------------------------------------------
    # Guild Updates
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> None:
        executor, _ = await fetch_audit_log_entry(
            after,
            discord.AuditLogAction.guild_update,
        )
        changes: list[tuple[str, str, bool]] = []

        if before.name != after.name:
            changes.append(("Name", f"`{before.name}` → `{after.name}`", False))

        if before.icon != after.icon:
            changes.append(("Icon", "Changed (see image)", False))

        if before.banner != after.banner:
            changes.append(("Banner", "Changed", False))

        if before.verification_level != after.verification_level:
            changes.append((
                "Verification Level",
                f"`{_VERIFICATION_LEVELS.get(before.verification_level, str(before.verification_level))}` → "
                f"`{_VERIFICATION_LEVELS.get(after.verification_level, str(after.verification_level))}`",
                False,
            ))

        if before.system_channel != after.system_channel:
            b_ch = before.system_channel.mention if before.system_channel else "None"
            a_ch = after.system_channel.mention if after.system_channel else "None"
            changes.append(("System Channel", f"{b_ch} → {a_ch}", True))

        if before.description != after.description:
            changes.append((
                "Description",
                f"**Before:** {before.description or '*None*'}\n**After:** {after.description or '*None*'}",
                False,
            ))

        if before.afk_channel != after.afk_channel:
            b_afk = before.afk_channel.mention if before.afk_channel else "None"
            a_afk = after.afk_channel.mention if after.afk_channel else "None"
            changes.append(("AFK Channel", f"{b_afk} → {a_afk}", True))

        if before.explicit_content_filter != after.explicit_content_filter:
            changes.append((
                "Explicit Content Filter",
                f"`{before.explicit_content_filter}` → `{after.explicit_content_filter}`",
                True,
            ))

        if not changes:
            return

        changes.insert(0, ("Updated By", format_actor(executor), True))

        embed = build_embed(
            event_type="server",
            title="⚙️ Server Settings Updated",
            colour=Colours.SERVER,
            fields=changes,
            thumbnail_url=after.icon.url if after.icon else None,
        )
        await send_log(after, "server_update", fallback="server", embed=embed)

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        """
        Fired when webhooks are created, deleted, or updated in a channel.
        We query the audit log to determine the specific action.
        """
        guild = channel.guild

        # Try to match a webhook-related audit log entry
        for action in (
            discord.AuditLogAction.webhook_create,
            discord.AuditLogAction.webhook_update,
            discord.AuditLogAction.webhook_delete,
        ):
            executor, reason = await fetch_audit_log_entry(
                guild, action, target_id=None, delay=0.3
            )
            if executor:
                action_strs = {
                    discord.AuditLogAction.webhook_create: ("🔗 Webhook Created", "create"),
                    discord.AuditLogAction.webhook_update: ("🔗 Webhook Updated", "update"),
                    discord.AuditLogAction.webhook_delete: ("🔗 Webhook Deleted", "delete"),
                }
                title, event_type = action_strs[action]
                fields: list[tuple[str, str, bool]] = [
                    ("Channel",    channel.mention + f" (`{channel.id}`)", True),
                    ("By",         format_actor(executor), True),
                ]
                if reason:
                    fields.append(("Reason", reason, False))

                embed = build_embed(
                    event_type=event_type,
                    title=title,
                    fields=fields,
                )
                await send_log(guild, "webhook_update", fallback="server", embed=embed)
                return

    # ------------------------------------------------------------------
    # Emojis
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: list[discord.Emoji],
        after: list[discord.Emoji],
    ) -> None:
        before_set = {e.id: e for e in before}
        after_set  = {e.id: e for e in after}

        added_ids   = set(after_set) - set(before_set)
        removed_ids = set(before_set) - set(after_set)

        for emoji_id in added_ids:
            emoji = after_set[emoji_id]
            executor, _ = await fetch_audit_log_entry(
                guild, discord.AuditLogAction.emoji_create, target_id=emoji.id
            )
            embed = build_embed(
                event_type="create",
                title="😀 Emoji Added",
                fields=[
                    ("Name",       f":{emoji.name}:", True),
                    ("Emoji",      str(emoji), True),
                    ("Added By",   format_actor(executor), True),
                    ("Emoji ID",   f"`{emoji.id}`", True),
                    ("Animated",   "Yes" if emoji.animated else "No", True),
                ],
                thumbnail_url=str(emoji.url),
            )
            await send_log(guild, "emoji_update", fallback="server", embed=embed)

        for emoji_id in removed_ids:
            emoji = before_set[emoji_id]
            executor, _ = await fetch_audit_log_entry(
                guild, discord.AuditLogAction.emoji_delete, target_id=emoji.id
            )
            embed = build_embed(
                event_type="delete",
                title="😢 Emoji Removed",
                fields=[
                    ("Name",       f":{emoji.name}:", True),
                    ("Removed By", format_actor(executor), True),
                    ("Emoji ID",   f"`{emoji.id}`", True),
                ],
            )
            await send_log(guild, "emoji_update", fallback="server", embed=embed)

    # ------------------------------------------------------------------
    # Stickers
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_stickers_update(
        self,
        guild: discord.Guild,
        before: list[discord.GuildSticker],
        after: list[discord.GuildSticker],
    ) -> None:
        before_set = {s.id: s for s in before}
        after_set  = {s.id: s for s in after}

        added_ids   = set(after_set) - set(before_set)
        removed_ids = set(before_set) - set(after_set)

        for sticker_id in added_ids:
            sticker = after_set[sticker_id]
            executor, _ = await fetch_audit_log_entry(
                guild, discord.AuditLogAction.sticker_create, target_id=sticker.id
            )
            embed = build_embed(
                event_type="create",
                title="🎨 Sticker Added",
                fields=[
                    ("Name",       sticker.name, True),
                    ("Description",sticker.description or "N/A", True),
                    ("Added By",   format_actor(executor), True),
                    ("Sticker ID", f"`{sticker.id}`", True),
                ],
                thumbnail_url=sticker.url,
            )
            await send_log(guild, "emoji_update", fallback="server", embed=embed)

        for sticker_id in removed_ids:
            sticker = before_set[sticker_id]
            executor, _ = await fetch_audit_log_entry(
                guild, discord.AuditLogAction.sticker_delete, target_id=sticker.id
            )
            embed = build_embed(
                event_type="delete",
                title="🗑️ Sticker Removed",
                fields=[
                    ("Name",        sticker.name, True),
                    ("Removed By",  format_actor(executor), True),
                    ("Sticker ID",  f"`{sticker.id}`", True),
                ],
            )
            await send_log(guild, "emoji_update", fallback="server", embed=embed)

    # ------------------------------------------------------------------
    # AutoMod Rule create/delete/update (config changes)
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_automod_rule_create(self, rule: discord.AutoModRule) -> None:
        guild = rule.guild
        executor, _ = await fetch_audit_log_entry(
            guild, discord.AuditLogAction.automod_rule_create, target_id=rule.id
        )
        embed = build_embed(
            event_type="create",
            title="🛡️ AutoMod Rule Created",
            fields=[
                ("Rule Name", rule.name, True),
                ("Created By", format_actor(executor), True),
                ("Enabled",   "Yes" if rule.enabled else "No", True),
                ("Rule ID",   f"`{rule.id}`", True),
            ],
        )
        await send_log(guild, "automod", fallback="server", embed=embed)

    @commands.Cog.listener()
    async def on_automod_rule_delete(self, rule: discord.AutoModRule) -> None:
        guild = rule.guild
        executor, _ = await fetch_audit_log_entry(
            guild, discord.AuditLogAction.automod_rule_delete, target_id=rule.id
        )
        embed = build_embed(
            event_type="delete",
            title="🛡️ AutoMod Rule Deleted",
            fields=[
                ("Rule Name",   rule.name, True),
                ("Deleted By",  format_actor(executor), True),
                ("Rule ID",     f"`{rule.id}`", True),
            ],
        )
        await send_log(guild, "automod", fallback="server", embed=embed)

    @commands.Cog.listener()
    async def on_automod_rule_update(self, rule: discord.AutoModRule) -> None:
        guild = rule.guild
        executor, _ = await fetch_audit_log_entry(
            guild, discord.AuditLogAction.automod_rule_update, target_id=rule.id
        )
        embed = build_embed(
            event_type="update",
            title="🛡️ AutoMod Rule Updated",
            fields=[
                ("Rule Name",  rule.name, True),
                ("Updated By", format_actor(executor), True),
                ("Enabled",    "Yes" if rule.enabled else "No", True),
                ("Rule ID",    f"`{rule.id}`", True),
            ],
        )
        await send_log(guild, "automod", fallback="server", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerLogs(bot))
