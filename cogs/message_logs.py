"""
cogs/message_logs.py — Message & Reaction Event Logger
=======================================================
Handles:
  - on_message_delete        Ghost ping detection, attachment listing
  - on_message_edit          Before/after content diff with jump link
  - on_bulk_message_delete   HTML transcript generation + file upload
  - on_raw_reaction_add      Reaction tracking
  - on_raw_reaction_remove   Reaction tracking
  - on_raw_reaction_clear    Full reaction clear tracking
"""

from __future__ import annotations

import asyncio
import difflib
import logging
from datetime import datetime, timezone
from typing import Sequence

import discord
from discord.ext import commands

from cogs.settings import send_log
from database.db import db
from utils.embed_builder import build_embed, fmt_user, fmt_channel, fmt_dt, Colours
from utils.i18n import t
from utils.transcript_generator import generate_html_transcript

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _message_age(created_at: datetime) -> str:
    """Return human-readable age of a message."""
    now = datetime.now(tz=timezone.utc)
    delta = now - created_at.replace(tzinfo=timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


def _compute_diff(before: str, after: str) -> str:
    """
    Produce a compact inline diff between two strings.
    Returns a code-block string showing removed/added lines.
    """
    before_lines = before.splitlines(keepends=True) or [""]
    after_lines  = after.splitlines(keepends=True) or [""]

    diff_lines: list[str] = []
    for line in difflib.unified_diff(
        before_lines,
        after_lines,
        lineterm="",
        n=2,
    ):
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        diff_lines.append(line)

    result = "".join(diff_lines).strip()
    if not result:
        return "(No textual difference detected)"
    # Truncate to 900 chars to fit Discord field limits
    if len(result) > 900:
        result = result[:897] + "…"
    return f"```diff\n{result}\n```"


def _truncate(text: str, limit: int = 1024) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _is_ignored(guild_id: int, msg: discord.Message) -> bool:
    """Return True if this message's author or channel is on the ignore list."""
    if await db.is_ignored(guild_id, "channel", msg.channel.id):
        return True
    if await db.is_ignored(guild_id, "user", msg.author.id):
        return True
    # Check author's roles
    if hasattr(msg.author, "roles"):
        for role in msg.author.roles:
            if await db.is_ignored(guild_id, "role", role.id):
                return True
    return False


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class MessageLogs(commands.Cog, name="MessageLogs"):
    """Logs all message-related events."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Cache: message_id → discord.Message (for edit diff)
        self._message_cache: dict[int, discord.Message] = {}

    # ------------------------------------------------------------------
    # on_message  (cache for edit diffs)
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        # Increment user's message counter in the database
        await db.increment_message_count(message.author.id, message.guild.id)

        # Keep a rolling cache of the last 2000 messages per bot restart
        self._message_cache[message.id] = message
        if len(self._message_cache) > 2000:
            oldest = next(iter(self._message_cache))
            del self._message_cache[oldest]

    # ------------------------------------------------------------------
    # on_message_delete
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if message.author.bot:
            return
        if await _is_ignored(message.guild.id, message):
            return

        guild = message.guild
        author = message.author
        channel = message.channel
        lifespan = _message_age(message.created_at)
        lang = await db.get_guild_language(guild.id)

        # ── Ghost Ping Detection ──────────────────────────────────────
        ghost_targets: list[str] = []
        for user in message.mentions:
            if not user.bot:
                ghost_targets.append(f"👤 {user.mention} (`{user.id}`)")
        for role in message.role_mentions:
            ghost_targets.append(f"🏷️ {role.mention} (`{role.id}`)")

        if ghost_targets:
            ghost_embed = build_embed(
                event_type="warn",
                title=t("ghost_ping_title", lang),
                description=t("ghost_ping_desc", lang, author=author.mention, channel=channel.mention, targets="\n".join(ghost_targets)),
                colour=Colours.WARN,
                fields=[
                    (t("user", lang),       fmt_user(author), True),
                    (t("channel", lang),    fmt_channel(channel), True),
                    (t("lifespan", lang),   lifespan, True),
                    (t("message_id", lang), f"`{message.id}`", True),
                    (t("sent_at", lang),    fmt_dt(message.created_at), True),
                ],
                author_name=str(author),
                author_icon_url=author.display_avatar.url,
            )
            await send_log(guild, "messages", embed=ghost_embed)

        # ── Standard Delete Embed ─────────────────────────────────────
        no_content = "*[بلا محتوى نصي]*" if lang == "ar" else "*[No text content]*"
        content = message.content or no_content
        if len(content) > 1000:
            content = content[:997] + "…"

        content_label = "المحتوى:" if lang == "ar" else "Content:"
        fields: list[tuple[str, str, bool]] = [
            (t("user", lang),       fmt_user(author), True),
            (t("channel", lang),    fmt_channel(channel), True),
            (t("lifespan", lang),   lifespan, True),
            (t("sent_at", lang),    fmt_dt(message.created_at), True),
            (t("message_id", lang), f"`{message.id}`", True),
        ]

        if message.reference:
            fields.append((t("reply_to", lang), f"`{message.reference.message_id}`", True))

        if message.attachments:
            att_lines = []
            for att in message.attachments:
                size_kb = att.size / 1024
                att_lines.append(f"📎 `{att.filename}` ({size_kb:.1f} KB)")
                if att.proxy_url:
                    att_lines.append(f"   └ URL: {att.proxy_url}")
            att_label = f"المرفقات ({len(message.attachments)})" if lang == "ar" else f"Attachments ({len(message.attachments)})"
            fields.append((
                att_label,
                "\n".join(att_lines)[:1024],
                False,
            ))

        embed = build_embed(
            event_type="delete",
            title=t("msg_deleted_title", lang),
            description=f"**{content_label}**\n{content}",
            fields=fields,
            author_name=str(author),
            author_icon_url=author.display_avatar.url,
        )
        await send_log(guild, "message_delete", fallback="messages", embed=embed)

    # ------------------------------------------------------------------
    # on_message_edit
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content:
            return  # Pin / embed unfurl — not a real edit
        if await _is_ignored(before.guild.id, before):
            return

        guild   = before.guild
        author  = before.author
        channel = before.channel
        lang    = await db.get_guild_language(guild.id)

        empty_str = "*(فارغ)*" if lang == "ar" else "*(empty)*"
        before_content = before.content or empty_str
        after_content  = after.content  or empty_str

        diff_text = _compute_diff(before_content, after_content)
        jump_url  = after.jump_url
        jump_text = f"[انقر للانتقال للرسالة]({jump_url})" if lang == "ar" else f"[Click to view message]({jump_url})"

        fields: list[tuple[str, str, bool]] = [
            (t("user", lang),       fmt_user(author), True),
            (t("channel", lang),    fmt_channel(channel), True),
            (t("jump", lang),       jump_text, True),
            (t("message_id", lang), f"`{before.id}`", True),
            (t("before", lang),     _truncate(before_content, 1020), False),
            (t("after", lang),      _truncate(after_content,  1020), False),
            (t("diff", lang),       diff_text, False),
        ]

        embed = build_embed(
            event_type="edit",
            title=t("msg_edited_title", lang),
            fields=fields,
            author_name=str(author),
            author_icon_url=author.display_avatar.url,
        )
        await send_log(guild, "message_edit", fallback="messages", embed=embed)

        # Update cache
        self._message_cache[after.id] = after

    # ------------------------------------------------------------------
    # on_bulk_message_delete
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_bulk_message_delete(
        self, messages: list[discord.Message]
    ) -> None:
        if not messages:
            return

        # Resolve guild from first available message
        guild = None
        for msg in messages:
            if msg.guild:
                guild = msg.guild
                break
        if guild is None:
            return

        channel = messages[0].channel
        count   = len(messages)
        lang    = await db.get_guild_language(guild.id)

        # Generate HTML transcript
        try:
            bio = await generate_html_transcript(
                messages,
                channel_name=getattr(channel, "name", "unknown"),
                guild_name=guild.name,
                extra_info=f"Bulk delete of {count} messages",
            )
        except Exception as exc:
            log.error("Transcript generation failed: %s", exc)
            bio = None

        desc_base = t("bulk_delete_desc", lang, count=count, channel=channel.mention)
        desc_att  = "\n" + t("transcript_attached", lang) if bio else ""

        embed = build_embed(
            event_type="delete",
            title=t("bulk_delete_title", lang, count=count),
            description=f"{desc_base}{desc_att}",
            fields=[
                (t("channel", lang),   fmt_channel(channel), True),
                (t("msg_count", lang), str(count), True),
            ],
        )

        file: discord.File | None = None
        if bio:
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"transcript_{ts}.html"
            file = discord.File(bio, filename=filename)

        await send_log(guild, "message_purge", fallback="messages", embed=embed, file=file)

    # ------------------------------------------------------------------
    # Reaction events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        await self._log_reaction(payload, added=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        await self._log_reaction(payload, added=False)

    async def _log_reaction(
        self,
        payload: discord.RawReactionActionEvent,
        *,
        added: bool,
    ) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        user = guild.get_member(payload.user_id) or self.bot.get_user(payload.user_id)
        if user and getattr(user, "bot", False):
            return

        channel = guild.get_channel(payload.channel_id)
        if channel and await db.is_ignored(guild.id, "channel", channel.id):
            return

        emoji = payload.emoji
        emoji_str = str(emoji)

        jump_url = (
            f"https://discord.com/channels/{payload.guild_id}/"
            f"{payload.channel_id}/{payload.message_id}"
        )

        event_type = "create" if added else "delete"
        title = "⭐ Reaction Added" if added else "💔 Reaction Removed"

        fields: list[tuple[str, str, bool]] = [
            ("User",      fmt_user(user), True),
            ("Emoji",     emoji_str, True),
            ("Channel",   f"<#{payload.channel_id}>", True),
            ("Message",   f"[Jump]({jump_url})", True),
            ("Message ID",f"`{payload.message_id}`", True),
        ]

        embed = build_embed(
            event_type=event_type,
            title=title,
            fields=fields,
            author_name=str(user) if user else f"User {payload.user_id}",
            author_icon_url=(
                user.display_avatar.url
                if user and hasattr(user, "display_avatar")
                else None
            ),
        )
        await send_log(guild, "reactions", fallback="messages", embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(
        self, payload: discord.RawReactionClearEvent
    ) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        jump_url = (
            f"https://discord.com/channels/{payload.guild_id}/"
            f"{payload.channel_id}/{payload.message_id}"
        )

        embed = build_embed(
            event_type="delete",
            title="🧹 All Reactions Cleared",
            description=f"All reactions were removed from a [message]({jump_url}).",
            fields=[
                ("Channel",    f"<#{payload.channel_id}>", True),
                ("Message ID", f"`{payload.message_id}`", True),
            ],
        )
        await send_log(guild, "reactions", fallback="messages", embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_clear_emoji(
        self, payload: discord.RawReactionClearEmojiEvent
    ) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        jump_url = (
            f"https://discord.com/channels/{payload.guild_id}/"
            f"{payload.channel_id}/{payload.message_id}"
        )

        embed = build_embed(
            event_type="delete",
            title="💔 Emoji Reactions Cleared",
            description=(
                f"All **{payload.emoji}** reactions were cleared from "
                f"[this message]({jump_url})."
            ),
            fields=[
                ("Emoji",      str(payload.emoji), True),
                ("Channel",    f"<#{payload.channel_id}>", True),
                ("Message ID", f"`{payload.message_id}`", True),
            ],
        )
        await send_log(guild, "reactions", fallback="messages", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageLogs(bot))
