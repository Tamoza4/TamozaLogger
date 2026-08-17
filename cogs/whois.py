"""
cogs/whois.py — User Inspection & Security Report Command
==========================================================
Provides /whois <user> — a comprehensive, single-embed security and
forensics report for any member or user in the server.

Features in ONE unified report message:
  1. Identity & Account  — Avatar, Mention, Tag, ID, Account Age, Display Name
  2. Server & Activity   — Joined At, Duration in Server, Nickname, Messages Sent, Voice State
  3. Roles & Permissions — Top Role, Role List, Elevated Permission Highlights
  4. Security Assessment — 0–100 Risk Score with automated severity-flagged checks
  5. History             — Recent Nickname and Username history from database
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.voice_logs import get_current_voice_session_duration
from database.db import db
from utils.embed_builder import (
    build_embed, fmt_dt, human_timedelta, account_age_warning, Colours,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security flag definitions
# ---------------------------------------------------------------------------

_SEVERITY_COLOUR = {
    "critical": 0xFF0000,
    "high":     0xFF6B35,
    "medium":   0xF7C59F,
    "low":      0xFFE66D,
    "info":     0x4ECDC4,
    "clean":    0x2ECC71,
}

_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🔵",
    "info":     "⚪",
    "clean":    "🟢",
}


def _age_days(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(tz=timezone.utc) - dt).days


def _check_security_flags(
    member: discord.Member | discord.User,
    *,
    guild: discord.Guild | None = None,
    nick_count: int = 0,
    username_count: int = 0,
) -> list[tuple[str, str, str]]:
    """
    Run automated security checks on a user.

    Returns
    -------
    list of (label, description, severity)
    """
    flags: list[tuple[str, str, str]] = []
    age_days = _age_days(member.created_at)

    # ── Account age ──────────────────────────────────────────────────
    if age_days < 1:
        flags.append(("Account < 1 day old", "Extremely new account — very high spam/raid risk.", "critical"))
    elif age_days < 7:
        flags.append(("Account < 7 days old", f"Account is only {age_days} day(s) old — new account warning.", "high"))
    elif age_days < 30:
        flags.append(("Account < 30 days old", f"Account is {age_days} days old — moderately new.", "medium"))
    else:
        flags.append(("Account age OK", f"Account is {age_days} days old.", "info"))

    # ── Default avatar ───────────────────────────────────────────────
    if member.default_avatar == member.display_avatar:
        flags.append(("No custom avatar", "User has default avatar — common on throwaway/bot accounts.", "medium"))

    # ── Bot flag ─────────────────────────────────────────────────────
    if getattr(member, "bot", False):
        flags.append(("Bot Account", "This user is a bot/application.", "info"))

    # ── Member-specific checks ───────────────────────────────────────
    if isinstance(member, discord.Member) and guild:

        # Timeout
        if member.timed_out_until:
            tu = member.timed_out_until.replace(tzinfo=timezone.utc)
            if tu > datetime.now(tz=timezone.utc):
                flags.append(("Currently Timed Out", f"Timeout expires {fmt_dt(tu)}.", "high"))

        # Dangerous permissions
        dangerous: list[str] = []
        perms = member.guild_permissions
        if perms.administrator:
            dangerous.append("ADMINISTRATOR")
        if perms.ban_members:
            dangerous.append("BAN_MEMBERS")
        if perms.kick_members:
            dangerous.append("KICK_MEMBERS")
        if perms.manage_guild:
            dangerous.append("MANAGE_GUILD")
        if perms.manage_roles:
            dangerous.append("MANAGE_ROLES")
        if perms.manage_channels:
            dangerous.append("MANAGE_CHANNELS")
        if perms.manage_webhooks:
            dangerous.append("MANAGE_WEBHOOKS")
        if perms.mention_everyone:
            dangerous.append("MENTION_EVERYONE")
        if perms.manage_messages:
            dangerous.append("MANAGE_MESSAGES")

        if dangerous:
            sev = "critical" if "ADMINISTRATOR" in dangerous else "high"
            flags.append((
                f"Elevated Permissions ({len(dangerous)})",
                "Has: " + ", ".join(f"`{p}`" for p in dangerous),
                sev,
            ))

        # Join date vs account creation
        if member.joined_at:
            join_age = _age_days(member.joined_at)
            if join_age < 1 and age_days < 7:
                flags.append(("New account joined recently", "Very new account joined server within last 24h.", "high"))

        # No roles
        real_roles = [r for r in member.roles if r.id != guild.id]
        if not real_roles and _age_days(member.joined_at or member.created_at) > 1:
            flags.append(("No roles assigned", "Member in server >1 day with no assigned roles.", "low"))

    # ── History flags ────────────────────────────────────────────────
    if username_count > 5:
        flags.append(("Frequent username changes", f"Changed username {username_count} time(s).", "medium"))
    if nick_count > 10:
        flags.append(("Frequent nickname changes", f"Changed nickname {nick_count} time(s) in this server.", "low"))

    return flags


def _score_from_flags(flags: list[tuple[str, str, str]]) -> tuple[int, str, int]:
    """
    Convert flags into a 0–100 safety score.
    Returns (score, label, colour_int).
    """
    penalty = 0
    weights = {"critical": 40, "high": 20, "medium": 10, "low": 5, "info": 0}
    for _, _, sev in flags:
        penalty += weights.get(sev, 0)

    score = max(0, 100 - penalty)

    if score >= 80:
        label = "🟢 Low Risk"
        colour = _SEVERITY_COLOUR["clean"]
    elif score >= 60:
        label = "🟡 Moderate Risk"
        colour = _SEVERITY_COLOUR["medium"]
    elif score >= 40:
        label = "🟠 High Risk"
        colour = _SEVERITY_COLOUR["high"]
    else:
        label = "🔴 Critical Risk"
        colour = _SEVERITY_COLOUR["critical"]

    return score, label, colour


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Whois(commands.Cog, name="Whois"):
    """User inspection and security report slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /whois
    # ------------------------------------------------------------------

    @app_commands.command(
        name="whois",
        description="Show a complete security, activity & forensics report for a user in 1 message.",
    )
    @app_commands.describe(user="The member or user to inspect.")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def whois(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild

        # ── Fetch history & message count from DB ────────────────────
        history_row = await db.fetchrow(
            "SELECT nick_history, username_history, message_count FROM member_history "
            "WHERE user_id = $1 AND guild_id = $2",
            user.id, guild.id,
        )
        nick_history: list[dict] = []
        username_history: list[dict] = []
        message_count: int = 0

        if history_row:
            message_count = history_row["message_count"] or 0
            try:
                raw_n = history_row["nick_history"]
                raw_u = history_row["username_history"]
                nick_history = json.loads(raw_n) if isinstance(raw_n, str) else list(raw_n or [])
                username_history = json.loads(raw_u) if isinstance(raw_u, str) else list(raw_u or [])
            except Exception:
                pass

        # ── Check server language preference ─────────────────────────
        srv_lang = await db.get_guild_language(guild.id)
        is_ar = (srv_lang == "ar")

        # ── Run security checks ──────────────────────────────────────
        flags = _check_security_flags(
            user,
            guild=guild,
            nick_count=len(nick_history),
            username_count=len(username_history),
        )
        score, risk_label, score_colour = _score_from_flags(flags)
        now = datetime.now(tz=timezone.utc)

        # ── Section 1: Identity & Account ─────────────────────────────
        age_str = account_age_warning(user.created_at)
        user_type = ("🤖 بوت" if is_ar else "🤖 Bot") if user.bot else ("👤 إنسان" if is_ar else "👤 Human")
        
        if is_ar:
            identity_val = (
                f"• **العضو:** {user.mention} (`{user.id}`)\n"
                f"• **اسم المستخدم:** `{user}`\n"
                f"• **الاسم المستعار:** {getattr(user, 'global_name', None) or '*لا يوجد*'}\n"
                f"• **تاريخ الإنشاء:** {fmt_dt(user.created_at)}\n"
                f"• **عمر الحساب:** {age_str}\n"
                f"• **النوع:** {user_type}"
            )
        else:
            identity_val = (
                f"• **User:** {user.mention} (`{user.id}`)\n"
                f"• **Username:** `{user}`\n"
                f"• **Display Name:** {getattr(user, 'global_name', None) or '*None*'}\n"
                f"• **Created:** {fmt_dt(user.created_at)}\n"
                f"• **Account Age:** {age_str}\n"
                f"• **Type:** {user_type}"
            )

        # ── Section 2: Server & Activity ──────────────────────────────
        joined_str = fmt_dt(user.joined_at) if user.joined_at else ("غير معروف" if is_ar else "Unknown")
        if user.joined_at:
            srv_secs = int((now - user.joined_at.replace(tzinfo=timezone.utc)).total_seconds())
            in_srv_str = human_timedelta(srv_secs)
        else:
            in_srv_str = "غير معروف" if is_ar else "Unknown"

        # Query total voice duration (closed sessions + active session)
        db_voice_secs = await db.get_total_voice_time(user.id, guild.id)
        active_voice_secs = get_current_voice_session_duration(user.id)
        total_voice_secs = db_voice_secs + active_voice_secs
        voice_time_str = human_timedelta(total_voice_secs) if total_voice_secs > 0 else ("0 ثوانٍ" if is_ar else "0 seconds")

        # Voice status string
        vs = user.voice
        if vs and vs.channel:
            vc_parts = [f"في {vs.channel.mention}" if is_ar else f"In {vs.channel.mention}"]
            if vs.self_mute:   vc_parts.append("🙊 مكتوم" if is_ar else "🙊 Muted")
            if vs.self_deaf:   vc_parts.append("🙉 أصم" if is_ar else "🙉 Deafened")
            if vs.mute:        vc_parts.append("🔇 مكتوم إدارياً" if is_ar else "🔇 Server-Muted")
            if vs.deaf:        vc_parts.append("🔕 أصم إدارياً" if is_ar else "🔕 Server-Deafened")
            if vs.self_stream: vc_parts.append("📺 يبث" if is_ar else "📺 Streaming")
            if vs.self_video:  vc_parts.append("📷 الكميرا مفعلة" if is_ar else "📷 Camera On")
            vc_str = " (" + ", ".join(vc_parts) + ")"
        else:
            vc_str = "ليس في روم صوتي" if is_ar else "Not in voice"

        timeout_str = ""
        if user.timed_out_until and user.timed_out_until.replace(tzinfo=timezone.utc) > now:
            t_label = "ينتهي الميوت المؤقت:" if is_ar else "Timed Out Until:"
            timeout_str = f"\n• ⏱️ **{t_label}** {fmt_dt(user.timed_out_until)}"

        if is_ar:
            activity_val = (
                f"• **تاريخ الانضمام:** {joined_str}\n"
                f"• **المدة في السيرفر:** {in_srv_str}\n"
                f"• **الاسم المحلي:** `{user.nick or '*لا يوجد*'}`\n"
                f"• 💬 **الرسائل المرسلة:** **{message_count:,}**\n"
                f"• 🔊 **الوقت في الرومات الصوتية:** **{voice_time_str}**\n"
                f"• **الحالة الصوتية:** {vc_str}"
                f"{timeout_str}"
            )
        else:
            activity_val = (
                f"• **Joined Server:** {joined_str}\n"
                f"• **Time in Server:** {in_srv_str}\n"
                f"• **Nickname:** `{user.nick or '*None*'}`\n"
                f"• 💬 **Messages Sent:** **{message_count:,}**\n"
                f"• 🔊 **Time in Voice:** **{voice_time_str}**\n"
                f"• **Voice State:** {vc_str}"
                f"{timeout_str}"
            )

        # ── Section 3: Roles & Permissions ────────────────────────────
        real_roles = sorted(
            [r for r in user.roles if r.id != guild.id],
            key=lambda r: r.position,
            reverse=True,
        )
        if real_roles:
            roles_fmt = " ".join(r.mention for r in real_roles[:12])
            if len(real_roles) > 12:
                roles_fmt += f" *…+{len(real_roles) - 12} المزيد*" if is_ar else f" *…+{len(real_roles) - 12} more*"
        else:
            roles_fmt = "*لا يوجد رتب*" if is_ar else "*No roles*"

        perms = user.guild_permissions
        elevated: list[str] = []
        perm_checks = [
            ("administrator",   "⚠️ مسؤول" if is_ar else "⚠️ Admin"),
            ("ban_members",     "🔨 حظر" if is_ar else "🔨 Ban"),
            ("kick_members",    "👢 طرد" if is_ar else "👢 Kick"),
            ("manage_guild",    "⚙️ إدارة السيرفر" if is_ar else "⚙️ Manage Server"),
            ("manage_roles",    "🏷️ إدارة الرتب" if is_ar else "🏷️ Manage Roles"),
            ("manage_channels", "📢 إدارة الرومات" if is_ar else "📢 Manage Channels"),
            ("manage_messages", "✂️ إدارة الرسائل" if is_ar else "✂️ Manage Messages"),
            ("manage_webhooks", "🔗 ويب هوك" if is_ar else "🔗 Webhooks"),
            ("mention_everyone","📣 منشن الجميع" if is_ar else "📣 Mention Everyone"),
            ("view_audit_log",  "📋 سجل التدقيق" if is_ar else "📋 Audit Log"),
            ("moderate_members","⏱️ تايم آوت" if is_ar else "⏱️ Timeout"),
        ]
        for attr, label in perm_checks:
            if getattr(perms, attr, False):
                elevated.append(label)

        elevated_str = ", ".join(f"`{p}`" for p in elevated) if elevated else ("*لا يوجد*" if is_ar else "*None*")

        if is_ar:
            roles_val = (
                f"• **أعلى رتبة:** {real_roles[0].mention if real_roles else '*لا يوجد*'}\n"
                f"• **الرتب ({len(real_roles)}):** {roles_fmt}\n"
                f"• **الصلاحيات العالية:** {elevated_str}"
            )
        else:
            roles_val = (
                f"• **Top Role:** {real_roles[0].mention if real_roles else '*None*'}\n"
                f"• **Roles ({len(real_roles)}):** {roles_fmt}\n"
                f"• **Elevated Perms:** {elevated_str}"
            )

        # ── Section 4: Security Flags ─────────────────────────────────
        flag_lines: list[str] = []
        for label, desc, sev in flags:
            emoji = _SEVERITY_EMOJI.get(sev, "⚪")
            flag_lines.append(f"{emoji} **{label}** — {desc}")

        security_val = "\n".join(flag_lines) if flag_lines else ("🟢 *لم يتم كشف أي مخاطر.*" if is_ar else "🟢 *No risk flags detected.*")

        # ── Section 5: History ────────────────────────────────────────
        history_parts: list[str] = []
        if nick_history:
            recent_nicks = nick_history[-3:][::-1]
            n_items = []
            for entry in recent_nicks:
                v = entry.get("value") or ("*ممسوح*" if is_ar else "*Cleared*")
                n_items.append(f"`{v}`")
            h_n_label = "• **الأسماء المستعارة الأخيرة:** " if is_ar else "• **Recent Nicks:** "
            history_parts.append(h_n_label + ", ".join(n_items))

        if username_history:
            recent_names = username_history[-3:][::-1]
            u_items = []
            for entry in recent_names:
                v = entry.get("value", "?")
                u_items.append(f"`{v}`")
            h_u_label = "• **أسماء المستخدم الأخيرة:** " if is_ar else "• **Recent Usernames:** "
            history_parts.append(h_u_label + ", ".join(u_items))

        history_val = "\n".join(history_parts) if history_parts else ("*لا يوجد أرشيف أسماء.*" if is_ar else "*No recorded name changes.*")

        # ── Assemble Single Master Embed ──────────────────────────────
        embed_title = f"🔍 التحقيق الجنائي والأمني — {user}" if is_ar else f"🔍 User Forensics — {user}"
        embed_desc = f"**مستوى الأمان: {score}/100 — {risk_label}**" if is_ar else f"**Safety Score: {score}/100 — {risk_label}**"
        footer_text = f"المستدعي: {interaction.user} • TamozaLogger" if is_ar else f"Requested by {interaction.user} • TamozaLogger"

        field_header_1 = "👤 الهوية والحساب" if is_ar else "👤 Identity & Account"
        field_header_2 = "📊 السيرفر والنشاط" if is_ar else "📊 Server & Activity"
        field_header_3 = "🏷️ الرتب والصلاحيات" if is_ar else "🏷️ Roles & Permissions"
        field_header_4 = "🛡️ التقييم الأمني" if is_ar else "🛡️ Security Assessment"
        field_header_5 = "📜 الأرشيف والسجل" if is_ar else "📜 History"

        embed = build_embed(
            event_type="neutral",
            title=embed_title,
            description=embed_desc,
            colour=score_colour,
            author_name=f"{user} ({user.id})",
            author_icon_url=user.display_avatar.url,
            thumbnail_url=user.display_avatar.url,
            fields=[
                (field_header_1, identity_val, False),
                (field_header_2, activity_val, False),
                (field_header_3, roles_val, False),
                (field_header_4, security_val, False),
                (field_header_5, history_val, False),
            ],
            footer_text=footer_text,
            timestamp=now,
        )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Whois(bot))
