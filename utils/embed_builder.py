"""
utils/embed_builder.py — Centralised Discord Embed Factory
===========================================================
All log embeds are constructed through this module to ensure a
consistent visual style, colour coding, and metadata across every cog.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import discord

from config import Colours


# ---------------------------------------------------------------------------
# Event-type → colour mapping
# ---------------------------------------------------------------------------

_CATEGORY_COLOURS: dict[str, int] = {
    # Positive / creation events
    "create":  Colours.CREATE,
    "join":    Colours.CREATE,
    "unban":   Colours.CREATE,

    # Negative / destruction events
    "delete":  Colours.DELETE,
    "leave":   Colours.DELETE,
    "ban":     Colours.DELETE,
    "kick":    Colours.DELETE,

    # Change / update events
    "update":  Colours.UPDATE,
    "edit":    Colours.UPDATE,
    "move":    Colours.UPDATE,

    # Voice events
    "voice":   Colours.VOICE,

    # Moderation events
    "mod":     Colours.MOD,
    "timeout": Colours.TIMEOUT,

    # Server / guild events
    "server":  Colours.SERVER,

    # Catch-all
    "neutral": Colours.NEUTRAL,
    "warn":    Colours.WARN,
}


def _resolve_colour(event_type: str) -> int:
    """Return the integer colour for a given event type keyword."""
    return _CATEGORY_COLOURS.get(event_type.lower(), Colours.NEUTRAL)


# ---------------------------------------------------------------------------
# Core embed builder
# ---------------------------------------------------------------------------

def build_embed(
    *,
    event_type: str,
    title: str,
    description: str = "",
    colour: int | None = None,
    author_name: str | None = None,
    author_icon_url: str | None = None,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
    footer_text: str | None = None,
    timestamp: datetime | None = None,
) -> discord.Embed:
    """
    Build a richly formatted log embed.

    Parameters
    ----------
    event_type:
        Keyword controlling colour (e.g. ``"create"``, ``"delete"``, ``"update"``).
    title:
        The embed title.
    description:
        The embed body text (supports Markdown).
    colour:
        Override the automatic colour resolution.
    author_name:
        Text shown in the author section (usually the acting user's name).
    author_icon_url:
        Icon shown beside the author text (usually the user's avatar URL).
    thumbnail_url:
        Small image in the top-right corner.
    image_url:
        Large image shown at the bottom of the embed.
    fields:
        List of ``(name, value, inline)`` tuples.
    footer_text:
        Override the footer text.  Defaults to "TamozaLogger".
    timestamp:
        The embed timestamp.  Defaults to ``datetime.now(UTC)``.

    Returns
    -------
    discord.Embed
    """
    resolved_colour = colour if colour is not None else _resolve_colour(event_type)
    ts = timestamp or datetime.now(tz=timezone.utc)

    embed = discord.Embed(
        title=title,
        description=description or discord.utils.MISSING,
        colour=resolved_colour,
        timestamp=ts,
    )

    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon_url)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if image_url:
        embed.set_image(url=image_url)

    for name, value, inline in (fields or []):
        # Discord field values must not be empty
        embed.add_field(name=name, value=value or "\u200b", inline=inline)

    embed.set_footer(text=footer_text or "TamozaLogger")

    return embed


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def user_embed(
    member: discord.Member | discord.User,
    *,
    event_type: str,
    title: str,
    description: str = "",
    fields: list[tuple[str, str, bool]] | None = None,
    timestamp: datetime | None = None,
    colour: int | None = None,
) -> discord.Embed:
    """
    Shorthand for user-centric embeds — pre-fills author with user
    display name + avatar.
    """
    return build_embed(
        event_type=event_type,
        title=title,
        description=description,
        colour=colour,
        author_name=str(member),
        author_icon_url=member.display_avatar.url,
        thumbnail_url=member.display_avatar.url,
        fields=fields,
        timestamp=timestamp,
    )


def channel_embed(
    channel: discord.abc.GuildChannel | discord.Thread,
    *,
    event_type: str,
    title: str,
    description: str = "",
    fields: list[tuple[str, str, bool]] | None = None,
    timestamp: datetime | None = None,
) -> discord.Embed:
    """Shorthand for channel-centric embeds."""
    return build_embed(
        event_type=event_type,
        title=title,
        description=description,
        fields=fields,
        timestamp=timestamp,
        footer_text=f"Channel ID: {channel.id} • TamozaLogger",
    )


def role_embed(
    role: discord.Role,
    *,
    event_type: str,
    title: str,
    description: str = "",
    fields: list[tuple[str, str, bool]] | None = None,
    timestamp: datetime | None = None,
) -> discord.Embed:
    """Shorthand for role-centric embeds — uses the role colour when creating."""
    colour = role.colour.value if role.colour.value else _resolve_colour(event_type)
    return build_embed(
        event_type=event_type,
        title=title,
        description=description,
        colour=colour,
        fields=fields,
        timestamp=timestamp,
        footer_text=f"Role ID: {role.id} • TamozaLogger",
    )


# ---------------------------------------------------------------------------
# Formatting helpers used across cogs
# ---------------------------------------------------------------------------

def fmt_user(user: discord.User | discord.Member | None, fallback: str = "Unknown") -> str:
    """Return a clickable mention + tag + ID string, e.g. ``@Username · Username#0 · `123` ``."""
    if user is None:
        return fallback
    return f"{user.mention} · {user} · `{user.id}`"


def fmt_channel(channel: discord.abc.GuildChannel | discord.Thread | None) -> str:
    """Return a channel mention or name."""
    if channel is None:
        return "Unknown channel"
    return f"{channel.mention} (`{channel.id}`)"


def fmt_dt(dt: datetime | None) -> str:
    """Return a Discord timestamp string, or 'N/A'."""
    if dt is None:
        return "N/A"
    ts = int(dt.timestamp())
    return f"<t:{ts}:F> (<t:{ts}:R>)"


def fmt_bool(value: bool) -> str:
    return "✅ Yes" if value else "❌ No"


def human_timedelta(seconds: int) -> str:
    """Convert a raw second count into a human-readable duration string."""
    if seconds < 0:
        seconds = 0
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    days, hrs = divmod(hours, 24)
    months, dys = divmod(days, 30)
    years, mths = divmod(months, 12)

    parts: list[str] = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if mths:
        parts.append(f"{mths} month{'s' if mths != 1 else ''}")
    if dys:
        parts.append(f"{dys} day{'s' if dys != 1 else ''}")
    if hrs and not years:
        parts.append(f"{hrs} hour{'s' if hrs != 1 else ''}")
    if mins and not (years or mths):
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    if not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    return ", ".join(parts)


def account_age_warning(created_at: datetime) -> str:
    """Return an age string, with a warning emoji for very new accounts."""
    now = datetime.now(tz=timezone.utc)
    delta = now - created_at.replace(tzinfo=timezone.utc)
    days = delta.days
    age_str = human_timedelta(int(delta.total_seconds()))

    if days < 7:
        return f"⚠️ **NEW ACCOUNT** — Created {age_str} ago"
    if days < 30:
        return f"🔶 Created {age_str} ago"
    return f"Created {age_str} ago"
