"""
cogs/member_logs.py — Member & Profile Event Logger
=====================================================
Handles:
  - on_member_join          Account age warning, join position, invite tracker
  - on_member_remove        Duration in server, kick detection
  - on_member_update        Nick changes, role diff + mod attribution, timeouts
  - on_user_update          Global username, avatar, banner changes
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

from cogs.settings import send_log
from database.db import db
from utils.audit_matcher import fetch_audit_log_entry, format_actor
from utils.embed_builder import (
    build_embed, user_embed, fmt_user, fmt_dt,
    account_age_warning, human_timedelta, Colours,
)
from utils.i18n import t

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory invite snapshot  {guild_id: {invite_code: uses}}
# Kept in sync by on_invite_create / on_invite_delete / on_member_join.
# Seeded from DB on bot ready (bot.py already calls bulk_sync_invites).
# ---------------------------------------------------------------------------
_invite_cache: dict[int, dict[str, int]] = {}


async def _build_memory_cache(guild: discord.Guild) -> dict[str, int]:
    """
    Fetch live invites from Discord and store them in the in-memory cache.
    Returns the {code: uses} snapshot.
    """
    try:
        invites = await guild.invites()
    except (discord.Forbidden, discord.HTTPException):
        return {}
    snapshot = {inv.code: (inv.uses or 0) for inv in invites}
    _invite_cache[guild.id] = snapshot
    # Also persist to DB so it survives restarts
    await db.bulk_sync_invites(guild.id, invites)
    return snapshot


async def _detect_used_invite(
    guild: discord.Guild,
) -> tuple[str | None, discord.Member | discord.User | None]:
    """
    Compare live invite uses against the pre-join snapshot to identify
    which invite was used by the joining member.

    Returns
    -------
    (invite_code, inviter)  or  (None, None) on failure.
    """
    try:
        current_invites = await guild.invites()
    except (discord.Forbidden, discord.HTTPException):
        return None, None

    # Use in-memory snapshot; fall back to DB if memory cache is cold
    if guild.id in _invite_cache:
        old_uses = _invite_cache[guild.id]
    else:
        cached_rows = await db.get_cached_invites(guild.id)
        old_uses = {row["invite_code"]: row["uses"] for row in cached_rows}

    # Build a map of current invite objects for easy lookup
    current_map: dict[str, discord.Invite] = {inv.code: inv for inv in current_invites}

    used_invite: discord.Invite | None = None
    for inv in current_invites:
        prev = old_uses.get(inv.code, 0)
        if (inv.uses or 0) > prev:
            used_invite = inv
            break

    # Update the in-memory snapshot and DB regardless of whether we found it
    new_snapshot = {inv.code: (inv.uses or 0) for inv in current_invites}
    _invite_cache[guild.id] = new_snapshot
    await db.bulk_sync_invites(guild.id, current_invites)

    if used_invite is None:
        return None, None

    inviter = used_invite.inviter  # discord.User | None
    return used_invite.code, inviter


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class MemberLogs(commands.Cog, name="MemberLogs"):
    """Logs all member and profile change events."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Invite cache maintenance
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Warm the in-memory invite cache from live Discord data on startup."""
        for guild in self.bot.guilds:
            await _build_memory_cache(guild)
        log.info("[InviteTracker] In-memory cache warmed for %d guilds.", len(self.bot.guilds))

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """Add a newly created invite to the in-memory cache."""
        if invite.guild is None:
            return
        gid = invite.guild.id
        if gid not in _invite_cache:
            _invite_cache[gid] = {}
        _invite_cache[gid][invite.code] = invite.uses or 0
        await db.upsert_invite(
            gid,
            invite.code,
            invite.inviter.id if invite.inviter else None,
            invite.uses or 0,
            invite.max_uses,
            invite.created_at,
            invite.expires_at,
        )
        log.debug("[InviteTracker] Cached new invite %s in guild %d", invite.code, gid)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """Remove a deleted invite from the in-memory cache."""
        if invite.guild is None:
            return
        gid = invite.guild.id
        _invite_cache.get(gid, {}).pop(invite.code, None)
        await db.delete_invite(gid, invite.code)
        log.debug("[InviteTracker] Removed invite %s from guild %d", invite.code, gid)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Seed invite cache when the bot is added to a new guild."""
        await _build_memory_cache(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        lang  = await db.get_guild_language(guild.id)

        # Record join time in DB
        await db.set_member_joined_at(member.id, guild.id, member.joined_at or datetime.now(tz=timezone.utc))

        # Account age
        age_str = account_age_warning(member.created_at)

        # Join position
        members_sorted = sorted(
            (m for m in guild.members if m.joined_at),
            key=lambda m: m.joined_at,
        )
        join_pos = next(
            (i + 1 for i, m in enumerate(members_sorted) if m.id == member.id),
            guild.member_count,
        )

        # Invite tracker
        invite_code, inviter = await _detect_used_invite(guild)
        if invite_code and inviter:
            invite_str = t("invited_by", lang, code=invite_code, inviter=fmt_user(inviter))
        elif invite_code:
            invite_str = f"Code `{invite_code}`"
        else:
            invite_str = t("invite_unknown", lang)

        fields: list[tuple[str, str, bool]] = [
            (t("user", lang),          fmt_user(member), True),
            ("المنشن" if lang == "ar" else "Mention", member.mention, True),
            (t("account_age", lang),   age_str, False),
            (t("join_pos", lang),      f"`{join_pos}` / {guild.member_count}", True),
            (t("joined_at", lang),     fmt_dt(member.joined_at), True),
            (t("invite_used", lang),   invite_str, False),
            (t("user_id", lang),       f"`{member.id}`", True),
        ]

        embed = build_embed(
            event_type="join",
            title=t("member_joined_title", lang),
            fields=fields,
            author_name=str(member),
            author_icon_url=member.display_avatar.url,
            thumbnail_url=member.display_avatar.url,
        )
        await send_log(guild, "member_join", fallback="members", embed=embed)

    # ------------------------------------------------------------------
    # on_member_remove
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        lang  = await db.get_guild_language(guild.id)

        # Check if this was a kick
        executor, reason = await fetch_audit_log_entry(
            guild,
            discord.AuditLogAction.kick,
            target_id=member.id,
        )

        # Compute time in server
        joined_at = await db.get_member_joined_at(member.id, guild.id)
        if joined_at is None:
            joined_at = member.joined_at
        if joined_at:
            if joined_at.tzinfo is None:
                joined_at = joined_at.replace(tzinfo=timezone.utc)
            delta = datetime.now(tz=timezone.utc) - joined_at
            duration_str = human_timedelta(int(delta.total_seconds()))
        else:
            duration_str = "غير معروف" if lang == "ar" else "Unknown"

        no_roles_str = "*لا يوجد*" if lang == "ar" else "None"
        roles_str = ", ".join(
            r.mention for r in member.roles if r.id != guild.id
        ) or no_roles_str

        if executor:
            # It was a kick
            event_type = "kick"
            title      = t("member_kicked_title", lang)
            colour     = Colours.MOD
            fields: list[tuple[str, str, bool]] = [
                (t("member", lang),         fmt_user(member), True),
                (t("kicked_by", lang),       format_actor(executor), True),
                (t("reason", lang),          reason or t("no_reason", lang), False),
                (t("time_in_server", lang),  duration_str, True),
                (t("roles", lang),           roles_str[:1024], False),
                (t("user_id", lang),         f"`{member.id}`", True),
            ]
            category = "mod"
        else:
            # Regular leave
            event_type = "leave"
            title      = t("member_left_title", lang)
            colour     = Colours.DELETE
            fields = [
                (t("member", lang),        fmt_user(member), True),
                (t("time_in_server", lang),duration_str, True),
                (t("joined_at", lang),     fmt_dt(joined_at), True),
                (t("roles", lang),         roles_str[:1024], False),
                (t("user_id", lang),       f"`{member.id}`", True),
            ]
            category = "members"

        embed = build_embed(
            event_type=event_type,
            title=title,
            colour=colour,
            fields=fields,
            author_name=str(member),
            author_icon_url=member.display_avatar.url,
            thumbnail_url=member.display_avatar.url,
        )
        log_key = "member_kick" if executor else "member_leave"
        await send_log(guild, log_key, fallback=category, embed=embed)

    # ------------------------------------------------------------------
    # on_member_update
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        guild = before.guild
        lang  = await db.get_guild_language(guild.id)

        # ── Nickname change ───────────────────────────────────────────
        if before.nick != after.nick:
            now = datetime.now(tz=timezone.utc)
            await db.append_nick_history(after.id, guild.id, after.nick, now)

            executor, reason = await fetch_audit_log_entry(
                guild,
                discord.AuditLogAction.member_update,
                target_id=after.id,
            )

            fallback_actor = "الشخص نفسه" if lang == "ar" else "Self"
            none_str = "*لا يوجد*" if lang == "ar" else "*None*"

            fields: list[tuple[str, str, bool]] = [
                (t("member", lang),       fmt_user(after), True),
                (t("updated_by", lang),   format_actor(executor, fallback=fallback_actor), True),
                (t("prev_nick", lang),    before.nick or none_str, True),
                (t("new_nick", lang),     after.nick  or none_str, True),
                (t("user_id", lang),      f"`{after.id}`", True),
            ]
            embed = build_embed(
                event_type="update",
                title=t("nick_changed_title", lang),
                fields=fields,
                author_name=str(after),
                author_icon_url=after.display_avatar.url,
            )
            await send_log(guild, "member_update", fallback="members", embed=embed)

        # ── Role changes ──────────────────────────────────────────────
        before_roles = set(before.roles)
        after_roles  = set(after.roles)
        added_roles   = after_roles - before_roles
        removed_roles = before_roles - after_roles

        if added_roles or removed_roles:
            executor, reason = await fetch_audit_log_entry(
                guild,
                discord.AuditLogAction.member_role_update,
                target_id=after.id,
            )

            fields = [(t("member", lang), fmt_user(after), True)]

            if executor:
                mod_label = "المشرف" if lang == "ar" else "Moderator"
                fields.append((mod_label, format_actor(executor), True))

            if added_roles:
                r_add_label = f"الرتب المضافة ({len(added_roles)})" if lang == "ar" else f"Roles Added ({len(added_roles)})"
                fields.append((
                    r_add_label,
                    ", ".join(r.mention for r in added_roles),
                    False,
                ))
            if removed_roles:
                r_rem_label = f"الرتب المزالة ({len(removed_roles)})" if lang == "ar" else f"Roles Removed ({len(removed_roles)})"
                fields.append((
                    r_rem_label,
                    ", ".join(r.mention for r in removed_roles),
                    False,
                ))

            fields.append((t("user_id", lang), f"`{after.id}`", True))

            embed = build_embed(
                event_type="update",
                title=t("roles_updated_title", lang),
                fields=fields,
                author_name=str(after),
                author_icon_url=after.display_avatar.url,
            )
            await send_log(guild, "member_update", fallback="members", embed=embed)

        # ── Timeout changes ───────────────────────────────────────────
        before_timeout = before.timed_out_until
        after_timeout  = after.timed_out_until

        if before_timeout != after_timeout:
            executor, reason = await fetch_audit_log_entry(
                guild,
                discord.AuditLogAction.member_update,
                target_id=after.id,
            )

            now = datetime.now(tz=timezone.utc)

            if after_timeout is not None:
                duration_secs = int(
                    (after_timeout.replace(tzinfo=timezone.utc) - now).total_seconds()
                )
                if duration_secs < 0:
                    duration_secs = 0
                duration_str = human_timedelta(duration_secs)

                if before_timeout is not None and after_timeout > before_timeout.replace(tzinfo=timezone.utc):
                    title = t("timeout_extended", lang)
                else:
                    title = t("timeout_applied", lang)

                fields = [
                    (t("member", lang),    fmt_user(after), True),
                    (t("by", lang),        format_actor(executor), True),
                    (t("duration", lang),  duration_str, True),
                    (t("expires_at", lang),fmt_dt(after_timeout), True),
                    (t("reason", lang),    reason or t("no_reason", lang), False),
                    (t("user_id", lang),   f"`{after.id}`", True),
                ]
                event_type = "timeout"
                colour     = Colours.TIMEOUT
            else:
                title      = t("timeout_removed", lang)
                event_type = "update"
                colour     = Colours.CREATE
                fields = [
                    (t("member", lang),  fmt_user(after), True),
                    (t("by", lang),      format_actor(executor), True),
                    (t("user_id", lang), f"`{after.id}`", True),
                ]

            embed = build_embed(
                event_type=event_type,
                title=title,
                colour=colour,
                fields=fields,
                author_name=str(after),
                author_icon_url=after.display_avatar.url,
            )
            await send_log(guild, "member_timeout", fallback="mod", embed=embed)

    # ------------------------------------------------------------------
    # on_user_update (global profile changes)
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_user_update(
        self, before: discord.User, after: discord.User
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        changes: list[tuple[str, str, bool]] = []

        # Username change
        if before.name != after.name:
            await db.append_username_history(after.id, after.name, now)
            changes.append(("Previous Username", f"`{before.name}`", True))
            changes.append(("New Username",      f"`{after.name}`", True))

        # Discriminator (legacy) or global name change
        if before.discriminator != after.discriminator:
            changes.append(("Previous Discriminator", f"`{before.discriminator}`", True))
            changes.append(("New Discriminator",      f"`{after.discriminator}`", True))

        # Global display name
        if getattr(before, "global_name", None) != getattr(after, "global_name", None):
            changes.append(("Previous Display Name", getattr(before, "global_name", None) or "*None*", True))
            changes.append(("New Display Name",      getattr(after, "global_name", None) or "*None*", True))

        # Avatar change
        if before.display_avatar != after.display_avatar:
            changes.append(("Avatar", "Changed (see thumbnail)", False))

        # Banner change (requires fetch)
        if before.banner != after.banner:
            changes.append(("Banner", "Changed", False))

        if not changes:
            return

        changes.append(("User ID", f"`{after.id}`", True))

        # We need to broadcast this to every mutual guild the user shares with the bot
        mutual_guilds = [g for g in self.bot.guilds if g.get_member(after.id)]

        embed = build_embed(
            event_type="update",
            title="🖼️ User Profile Updated",
            fields=changes,
            author_name=str(after),
            author_icon_url=after.display_avatar.url,
            thumbnail_url=after.display_avatar.url,
        )

        for guild in mutual_guilds:
            await send_log(guild, "user_update", fallback="members", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MemberLogs(bot))
