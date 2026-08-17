"""
cogs/voice_logs.py — Voice & Stage Channel Event Logger
=========================================================
Handles on_voice_state_update for:
  - Join / Leave / Move between voice channels
      ↳ Differentiates self-action vs moderator force-disconnect / force-move
        via AuditLogAction.member_disconnect and AuditLogAction.member_move
  - Self-mute / server-mute, self-deafen / server-deafen
  - Screen sharing (stream) and camera (video) toggles
  - Stage speaker / audience transitions and topic changes
  - Voice session duration tracking via the database

Attribution logic
-----------------
Discord does not fire a separate event for force-disconnect or force-move.
Both appear as a regular on_voice_state_update.  To detect moderation, we:
  1. Sleep 0.5 s to let the audit log entry propagate.
  2. Fetch the most recent member_disconnect / member_move audit log entry.
  3. Accept the entry only if it was created within AUDIT_THRESHOLD seconds
     of the voice-state event (avoids false attribution from old entries).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import discord
from discord.ext import commands

from cogs.settings import send_log
from database.db import db
from utils.audit_matcher import fetch_audit_log_entry, format_actor
from utils.embed_builder import (
    build_embed, fmt_user, human_timedelta, Colours,
)
from utils.i18n import t

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
# Maximum age (in seconds) for an audit log entry to be considered relevant
AUDIT_THRESHOLD: float = 2.0
# Delay before querying audit log to allow Discord's API propagation
AUDIT_DELAY:     float = 0.5

# ── Session tracking ──────────────────────────────────────────────────────────
# user_id → voice session DB row ID  (for duration recording in PostgreSQL)
_voice_sessions: dict[int, int] = {}
# user_id → UTC join datetime  (for fast in-memory duration calc)
_voice_join_times: dict[int, datetime] = {}


def get_current_voice_session_duration(user_id: int) -> int:
    """Return elapsed seconds of user's active voice session, or 0 if not in VC."""
    join_time = _voice_join_times.get(user_id)
    if not join_time:
        return 0
    now = datetime.now(tz=timezone.utc)
    return int((now - join_time).total_seconds())


# ── Audit-log helpers ─────────────────────────────────────────────────────────

async def _find_recent_audit_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: int,
    after_dt: datetime,
) -> Optional[discord.AuditLogEntry]:
    """
    Return the first audit log entry for *action* whose target matches
    *target_id* and which falls within AUDIT_THRESHOLD of *after_dt*.
    Used for member-targeted actions (role updates, member_update, etc.).
    """
    me = guild.me
    if not me or not me.guild_permissions.view_audit_log:
        return None

    deadline = after_dt + timedelta(seconds=AUDIT_THRESHOLD)
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            entry_time = entry.created_at
            if entry_time < after_dt:
                break
            if entry_time > deadline:
                continue
            if hasattr(entry.target, "id") and entry.target.id == target_id:
                return entry
    except discord.Forbidden:
        log.warning("[AuditLog] Forbidden querying audit logs in %s.", guild.name)
    except discord.HTTPException as exc:
        log.warning("[AuditLog] HTTP error querying audit logs in %s: %s", guild.name, exc)
    return None


async def _find_mod_action(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    event_time: datetime,
    *,
    target_channel_id: int | None = None,
    excluded_user_id: int | None = None,
    max_retries: int = 3,
    retry_delay: float = 0.5,
) -> Optional[discord.AuditLogEntry]:
    """
    Search for a recent audit log entry for *action* (member_move / member_disconnect)
    with a retry loop to handle Discord API propagation latency.

    Parameters
    ----------
    guild:
        The target guild.
    action:
        AuditLogAction.member_move or AuditLogAction.member_disconnect.
    event_time:
        The timestamp when on_voice_state_update fired.
    target_channel_id:
        For member_move, optionally match entry.extra.channel.id to ensure
        the entry is specifically for the destination channel.
    excluded_user_id:
        The ID of the member who was moved/disconnected (to avoid attributing self-actions).
    max_retries:
        How many attempts to find the entry.
    retry_delay:
        Seconds to wait between retry attempts.
    """
    me = guild.me
    if not me or not me.guild_permissions.view_audit_log:
        log.debug(
            "[AuditLog] Bot lacks view_audit_log in %s — skipping %s lookup.",
            guild.name, action,
        )
        return None

    # Search window: up to 10s before event_time and up to 5s after (covers clock skew & propagation)
    window_start = event_time - timedelta(seconds=10)
    window_end   = event_time + timedelta(seconds=5)

    for attempt in range(max_retries):
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                entry_time = entry.created_at

                # Stop scanning older entries beyond window_start
                if entry_time < window_start:
                    break

                if window_start <= entry_time <= window_end:
                    # Ignore entry if the executor is the user themselves (e.g. self-actions)
                    if excluded_user_id and entry.user and entry.user.id == excluded_user_id:
                        continue

                    # If this is member_move and target_channel_id is specified, verify destination channel
                    if action == discord.AuditLogAction.member_move and target_channel_id:
                        extra_ch = getattr(entry.extra, "channel", None)
                        if extra_ch and hasattr(extra_ch, "id"):
                            if extra_ch.id == target_channel_id:
                                return entry
                        else:
                            # If extra.channel is missing from Discord payload, still accept
                            return entry
                    else:
                        return entry

        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning("[AuditLog] Error querying audit logs in %s: %s", guild.name, exc)
            return None

        # Wait before retrying to allow Discord's audit log to propagate
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)

    return None






# ── Cog ───────────────────────────────────────────────────────────────────────

class VoiceLogs(commands.Cog, name="VoiceLogs"):
    """Logs all voice and stage channel state changes with moderator attribution."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ──────────────────────────────────────────────────────────────────────────
    # Main listener
    # ──────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after:  discord.VoiceState,
    ) -> None:
        """
        Fired whenever a guild member's voice state changes.
        Dispatches to focused helpers for each change type.
        """
        guild = member.guild
        if member.bot:
            return

        # ── 1. Channel join / leave / move ────────────────────────────
        if before.channel != after.channel:
            await self._handle_channel_change(guild, member, before, after)

        # ── Fetch lang once for the remaining non-channel checks ──────
        lang = await db.get_guild_language(guild.id)

        # ── 2. Server mute/unmute (administrative) ────────────────────
        if before.mute != after.mute:
            executor, _ = await fetch_audit_log_entry(
                guild,
                discord.AuditLogAction.member_update,
                target_id=member.id,
            )
            title  = t("server_muted", lang) if after.mute else t("server_unmuted", lang)
            colour = Colours.MOD if after.mute else Colours.CREATE
            embed  = build_embed(
                event_type="mod",
                title=title,
                colour=colour,
                fields=[
                    (t("member",  lang), fmt_user(member), True),
                    (t("by",      lang), format_actor(executor), True),
                    (t("channel", lang), after.channel.mention if after.channel else "N/A", True),
                    (t("user_id", lang), f"`{member.id}`", True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_state", fallback="voice", embed=embed)

        # ── 3. Server deafen/undeafen (administrative) ────────────────
        if before.deaf != after.deaf:
            executor, _ = await fetch_audit_log_entry(
                guild,
                discord.AuditLogAction.member_update,
                target_id=member.id,
            )
            title  = t("server_deafened", lang) if after.deaf else t("server_undeafened", lang)
            colour = Colours.MOD if after.deaf else Colours.CREATE
            embed  = build_embed(
                event_type="mod",
                title=title,
                colour=colour,
                fields=[
                    (t("member",  lang), fmt_user(member), True),
                    (t("by",      lang), format_actor(executor), True),
                    (t("channel", lang), after.channel.mention if after.channel else "N/A", True),
                    (t("user_id", lang), f"`{member.id}`", True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_state", fallback="voice", embed=embed)

        # ── 4. Self-mute toggle ───────────────────────────────────────
        if before.self_mute != after.self_mute:
            title = t("mic_muted", lang) if after.self_mute else t("mic_unmuted", lang)
            embed = build_embed(
                event_type="voice",
                title=title,
                colour=Colours.VOICE,
                fields=[
                    (t("member",  lang), fmt_user(member), True),
                    (t("channel", lang), after.channel.mention if after.channel else "N/A", True),
                    (t("user_id", lang), f"`{member.id}`", True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_state", fallback="voice", embed=embed)

        # ── 5. Self-deafen toggle ─────────────────────────────────────
        if before.self_deaf != after.self_deaf:
            title = t("headset_off", lang) if after.self_deaf else t("headset_on", lang)
            embed = build_embed(
                event_type="voice",
                title=title,
                colour=Colours.VOICE,
                fields=[
                    (t("member",  lang), fmt_user(member), True),
                    (t("channel", lang), after.channel.mention if after.channel else "N/A", True),
                    (t("user_id", lang), f"`{member.id}`", True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_state", fallback="voice", embed=embed)

        # ── 6. Screen share (stream) toggle ──────────────────────────
        if before.self_stream != after.self_stream:
            title = t("stream_start", lang) if after.self_stream else t("stream_stop", lang)
            embed = build_embed(
                event_type="voice",
                title=title,
                colour=Colours.VOICE,
                fields=[
                    (t("member",  lang), fmt_user(member), True),
                    (t("channel", lang), after.channel.mention if after.channel else "N/A", True),
                    (t("user_id", lang), f"`{member.id}`", True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_state", fallback="voice", embed=embed)

        # ── 7. Camera (video) toggle ──────────────────────────────────
        if before.self_video != after.self_video:
            title = t("cam_on", lang) if after.self_video else t("cam_off", lang)
            embed = build_embed(
                event_type="voice",
                title=title,
                colour=Colours.VOICE,
                fields=[
                    (t("member",  lang), fmt_user(member), True),
                    (t("channel", lang), after.channel.mention if after.channel else "N/A", True),
                    (t("user_id", lang), f"`{member.id}`", True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_state", fallback="voice", embed=embed)

        # ── 8. Stage speaker / audience transition ────────────────────
        if before.suppress != after.suppress:
            if after.suppress:
                title = "🎙️ Moved to Audience" if lang == "en" else "🎙️ نُقل إلى الجمهور"
            else:
                title = "🎙️ Became a Speaker" if lang == "en" else "🎙️ أصبح متحدثاً"
            embed = build_embed(
                event_type="voice",
                title=title,
                colour=Colours.VOICE,
                fields=[
                    (t("member",  lang), fmt_user(member), True),
                    ("Stage" if lang == "en" else "المسرح",
                     after.channel.mention if after.channel else "N/A", True),
                    (t("user_id", lang), f"`{member.id}`", True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice", embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # Channel join / leave / move  (with force-disconnect / force-move detection)
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_channel_change(
        self,
        guild:  discord.Guild,
        member: discord.Member,
        before: discord.VoiceState,
        after:  discord.VoiceState,
    ) -> None:
        """
        Handle a member changing voice channels.

        Three cases:
          • LEAVE  (after.channel is None)  → check for force-disconnect
          • JOIN   (before.channel is None) → normal join; open DB session
          • MOVE   (both channels set)      → check for force-move
        """
        event_time = datetime.now(tz=timezone.utc)
        lang       = await db.get_guild_language(guild.id)

        # ── LEAVE ─────────────────────────────────────────────────────
        if after.channel is None:
            await self._handle_leave(guild, member, before, event_time, lang)

        # ── JOIN ──────────────────────────────────────────────────────
        elif before.channel is None:
            await self._handle_join(guild, member, after, event_time, lang)

        # ── MOVE ──────────────────────────────────────────────────────
        else:
            await self._handle_move(guild, member, before, after, event_time, lang)

    # ── LEAVE helper ──────────────────────────────────────────────────────────

    async def _handle_leave(
        self,
        guild:      discord.Guild,
        member:     discord.Member,
        before:     discord.VoiceState,
        event_time: datetime,
        lang:       str,
    ) -> None:
        """
        Close the voice session, then determine whether the member left
        voluntarily or was force-disconnected by a moderator.

        Force-disconnect detection:
          • Wait AUDIT_DELAY seconds for Discord's audit log to propagate.
          • Look for a fresh AuditLogAction.member_disconnect entry that
            targets this member within AUDIT_THRESHOLD seconds.
        """
        # ── Close voice session ──────────────────────────────────────
        session_id = _voice_sessions.pop(member.id, None)
        join_time  = _voice_join_times.pop(member.id, None)

        if join_time:
            duration_secs = int((event_time - join_time).total_seconds())
            duration_str  = human_timedelta(duration_secs)
        else:
            duration_str = "غير معروف" if lang == "ar" else "Unknown"

        if session_id:
            try:
                await db.close_voice_session(session_id, event_time)
            except Exception as exc:
                log.warning("Failed to close voice session %d: %s", session_id, exc)

        # ── Audit-log check: force-disconnect? ───────────────────────
        audit_entry = await _find_mod_action(
            guild,
            discord.AuditLogAction.member_disconnect,
            event_time,
            excluded_user_id=member.id,
            max_retries=3,
            retry_delay=0.6,
        )

        if audit_entry is not None:
            # ── Forced Disconnect by Moderator ───────────────────────
            moderator = audit_entry.user
            mod_str   = (
                f"{moderator.mention} · {moderator} · `{moderator.id}`"
                if moderator else "Unknown Moderator"
            )
            if lang == "ar":
                title        = "🔴🔨 فصل قسري من روم صوتي"
                channel_lbl  = "الروم"
                duration_lbl = "مدة الجلسة"
                mod_lbl      = "المشرف"
                user_id_lbl  = "معرف العضو"
                ts_lbl       = "الوقت"
            else:
                title        = "🔴🔨 Force Disconnected from Voice"
                channel_lbl  = "Channel"
                duration_lbl = "Session Duration"
                mod_lbl      = "Disconnected By"
                user_id_lbl  = "User ID"
                ts_lbl       = "Timestamp"

            embed = discord.Embed(
                title=title,
                colour=discord.Colour.from_rgb(220, 53, 69),   # vivid red
                timestamp=event_time,
            )
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name=t("member", lang),  value=fmt_user(member),  inline=True)
            embed.add_field(name=channel_lbl,         value=before.channel.mention, inline=True)
            embed.add_field(name=duration_lbl,        value=duration_str,     inline=True)
            embed.add_field(name=mod_lbl,             value=mod_str,          inline=False)
            embed.add_field(name=user_id_lbl,         value=f"`{member.id}`", inline=True)
            embed.add_field(name=ts_lbl,              value=discord.utils.format_dt(event_time, "F"), inline=True)
            embed.set_footer(text=f"Target ID: {member.id} | Moderator ID: {moderator.id if moderator else 'N/A'}")
            await send_log(guild, "voice_disconnect", fallback="voice", embed=embed)

        else:
            # ── Self-disconnect / connection drop ─────────────────────
            embed = build_embed(
                event_type="leave",
                title=t("vc_left", lang),
                colour=Colours.DELETE,
                fields=[
                    (t("member",   lang), fmt_user(member),          True),
                    (t("channel",  lang), before.channel.mention,    True),
                    (t("duration", lang), duration_str,              True),
                    (t("user_id",  lang), f"`{member.id}`",          True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_leave", fallback="voice", embed=embed)

    # ── JOIN helper ───────────────────────────────────────────────────────────

    async def _handle_join(
        self,
        guild:      discord.Guild,
        member:     discord.Member,
        after:      discord.VoiceState,
        event_time: datetime,
        lang:       str,
    ) -> None:
        """Open a voice session and emit a join embed."""
        _voice_join_times[member.id] = event_time
        try:
            session_id = await db.open_voice_session(
                member.id, guild.id, after.channel.id
            )
            _voice_sessions[member.id] = session_id
        except Exception as exc:
            log.warning("Failed to open voice session: %s", exc)

        embed = build_embed(
            event_type="join",
            title=t("vc_joined", lang),
            colour=Colours.CREATE,
            fields=[
                (t("member",  lang), fmt_user(member),       True),
                (t("channel", lang), after.channel.mention,  True),
                (t("user_id", lang), f"`{member.id}`",       True),
            ],
            author_name=str(member),
            author_icon_url=member.display_avatar.url,
        )
        await send_log(guild, "voice_join", fallback="voice", embed=embed)

    # ── MOVE helper ───────────────────────────────────────────────────────────

    async def _handle_move(
        self,
        guild:      discord.Guild,
        member:     discord.Member,
        before:     discord.VoiceState,
        after:      discord.VoiceState,
        event_time: datetime,
        lang:       str,
    ) -> None:
        """
        Determine whether a channel switch was self-initiated or a force-move
        by a moderator (AuditLogAction.member_move).

        Force-move detection:
          • Wait AUDIT_DELAY seconds for Discord's audit log to propagate.
          • Look for a fresh AuditLogAction.member_move entry that targets
            this member within AUDIT_THRESHOLD seconds.
        """
        # ── Audit-log check: force-move? ─────────────────────────────
        # Retry loop + channel match + 10s window
        audit_entry = await _find_mod_action(
            guild,
            discord.AuditLogAction.member_move,
            event_time,
            target_channel_id=after.channel.id if after.channel else None,
            excluded_user_id=member.id,
            max_retries=3,
            retry_delay=0.6,
        )

        if audit_entry is not None:
            # ── Forced Move by Moderator ─────────────────────────────
            moderator = audit_entry.user
            mod_str   = (
                f"{moderator.mention} · {moderator} · `{moderator.id}`"
                if moderator else "Unknown Moderator"
            )
            if lang == "ar":
                title       = "🔀🔨 نقل قسري إلى روم صوتي"
                from_lbl    = "من الروم"
                to_lbl      = "إلى الروم"
                mod_lbl     = "المشرف"
                user_id_lbl = "معرف العضو"
                ts_lbl      = "الوقت"
            else:
                title       = "🔀🔨 Force Moved to Voice Channel"
                from_lbl    = "From Channel"
                to_lbl      = "To Channel"
                mod_lbl     = "Moved By"
                user_id_lbl = "User ID"
                ts_lbl      = "Timestamp"

            embed = discord.Embed(
                title=title,
                colour=discord.Colour.from_rgb(255, 140, 0),   # orange
                timestamp=event_time,
            )
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name=t("member", lang), value=fmt_user(member),         inline=False)
            embed.add_field(name=from_lbl,           value=before.channel.mention,  inline=True)
            embed.add_field(name=to_lbl,             value=after.channel.mention,   inline=True)
            embed.add_field(name=mod_lbl,            value=mod_str,                 inline=False)
            embed.add_field(name=user_id_lbl,        value=f"`{member.id}`",        inline=True)
            embed.add_field(name=ts_lbl,             value=discord.utils.format_dt(event_time, "F"), inline=True)
            embed.set_footer(text=f"Target ID: {member.id} | Moderator ID: {moderator.id if moderator else 'N/A'}")
            await send_log(guild, "voice_force_move", fallback="voice_move", embed=embed)

        else:
            # ── Self-initiated channel switch ─────────────────────────
            embed = build_embed(
                event_type="move",
                title=t("vc_moved", lang),
                colour=Colours.VOICE,
                fields=[
                    (t("member",  lang), fmt_user(member),        True),
                    (t("from",    lang), before.channel.mention,  True),
                    (t("to",      lang), after.channel.mention,   True),
                    (t("user_id", lang), f"`{member.id}`",        True),
                ],
                author_name=str(member),
                author_icon_url=member.display_avatar.url,
            )
            await send_log(guild, "voice_move", fallback="voice", embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # Stage topic changes
    # ──────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_stage_instance_create(self, stage: discord.StageInstance) -> None:
        """Log the start of a stage event."""
        guild = stage.guild
        executor, _ = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.stage_instance_create,
        )
        embed = build_embed(
            event_type="create",
            title="🎤 Stage Started",
            colour=Colours.CREATE,
            fields=[
                ("Topic",   stage.topic or "No topic", True),
                ("Channel", f"<#{stage.channel_id}>",  True),
                ("By",      format_actor(executor),     True),
            ],
        )
        await send_log(guild, "voice", embed=embed)

    @commands.Cog.listener()
    async def on_stage_instance_delete(self, stage: discord.StageInstance) -> None:
        """Log the end of a stage event."""
        guild = stage.guild
        executor, _ = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.stage_instance_delete,
        )
        embed = build_embed(
            event_type="delete",
            title="🎤 Stage Ended",
            colour=Colours.DELETE,
            fields=[
                ("Topic",   stage.topic or "No topic", True),
                ("Channel", f"<#{stage.channel_id}>",  True),
                ("By",      format_actor(executor),     True),
            ],
        )
        await send_log(guild, "voice", embed=embed)

    @commands.Cog.listener()
    async def on_stage_instance_update(
        self, before: discord.StageInstance, after: discord.StageInstance
    ) -> None:
        """Log stage topic changes."""
        if before.topic == after.topic:
            return
        guild = after.guild
        executor, _ = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.stage_instance_update,
        )
        embed = build_embed(
            event_type="update",
            title="🎤 Stage Topic Changed",
            colour=Colours.UPDATE,
            fields=[
                ("Previous Topic", before.topic or "None", False),
                ("New Topic",      after.topic  or "None", False),
                ("Channel",        f"<#{after.channel_id}>", True),
                ("By",             format_actor(executor),   True),
            ],
        )
        await send_log(guild, "voice", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceLogs(bot))
