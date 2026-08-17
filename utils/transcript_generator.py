"""
utils/transcript_generator.py — Self-Contained HTML Discord Transcript
=======================================================================
Generates a fully self-contained, dark-theme HTML file that mimics the
Discord UI.  All CSS is inlined — no external CDN dependencies.

Usage
-----
    from utils.transcript_generator import generate_html_transcript

    bio = await generate_html_transcript(messages)
    file = discord.File(bio, filename="transcript.html")
    await log_channel.send(file=file)
"""

from __future__ import annotations

import html
import io
from datetime import datetime, timezone
from typing import Sequence

import discord

from config import TRANSCRIPT_MAX_MESSAGES

# ---------------------------------------------------------------------------
# CSS — Discord dark theme approximation (100 % inlined)
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background: #313338;
    color: #dbdee1;
    font-family: 'gg sans', 'Noto Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 16px;
    line-height: 1.375;
}

header {
    background: #1e1f22;
    border-bottom: 1px solid #232428;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    position: sticky;
    top: 0;
    z-index: 100;
}
header .channel-name {
    font-size: 1.1rem;
    font-weight: 700;
    color: #f2f3f5;
}
header .meta {
    color: #949ba4;
    font-size: 0.85rem;
    margin-left: auto;
}

.messages-container {
    padding: 20px 20px 40px 20px;
    max-width: 960px;
    margin: 0 auto;
}

.message-group {
    display: flex;
    gap: 16px;
    padding: 4px 0;
    margin-bottom: 2px;
    border-radius: 4px;
    transition: background 0.1s;
}
.message-group:hover {
    background: #2e3035;
}

.avatar-col {
    flex-shrink: 0;
    width: 40px;
    padding-top: 2px;
}
.avatar-col img {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
    background: #5865f2;
}
.avatar-placeholder {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: #5865f2;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-weight: 700;
    font-size: 1rem;
}

.content-col {
    flex: 1;
    min-width: 0;
}
.message-header {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 2px;
}
.username {
    font-weight: 600;
    font-size: 1rem;
    color: #f2f3f5;
}
.bot-badge {
    background: #5865f2;
    color: #fff;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}
.timestamp {
    color: #80848e;
    font-size: 0.75rem;
}
.message-content {
    color: #dbdee1;
    word-break: break-word;
    white-space: pre-wrap;
}
.message-content.deleted {
    color: #f23f43;
    font-style: italic;
    text-decoration: line-through;
    opacity: 0.7;
}
.edited-badge {
    color: #80848e;
    font-size: 0.7rem;
    margin-left: 4px;
}

.attachment {
    margin-top: 6px;
    display: inline-block;
    background: #2b2d31;
    border: 1px solid #1e1f22;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 0.85rem;
    color: #00a8fc;
    max-width: 400px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.attachment::before { content: "📎 "; }

.embed-wrapper {
    margin-top: 6px;
    border-left: 4px solid #5865f2;
    background: #2b2d31;
    border-radius: 0 4px 4px 0;
    padding: 10px 14px;
    max-width: 520px;
}
.embed-title {
    font-weight: 700;
    color: #e3e5e8;
    margin-bottom: 4px;
}
.embed-description {
    font-size: 0.9rem;
    color: #dbdee1;
}

.reply-preview {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
    opacity: 0.7;
    font-size: 0.82rem;
    color: #949ba4;
}
.reply-preview::before {
    content: "↩";
    font-size: 0.9rem;
}

.date-divider {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 18px 0 10px 0;
    color: #80848e;
    font-size: 0.78rem;
    font-weight: 600;
}
.date-divider::before, .date-divider::after {
    content: "";
    flex: 1;
    height: 1px;
    background: #3f4147;
}

footer {
    text-align: center;
    color: #4e5058;
    font-size: 0.78rem;
    padding: 20px;
    border-top: 1px solid #232428;
    margin-top: 20px;
}
"""

# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


def _ts(dt: datetime) -> str:
    """Format a datetime for display in the transcript."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d/%m/%Y %H:%M UTC")


def _avatar_html(member: discord.Member | discord.User | None, *, size: int = 40) -> str:
    """Return an <img> tag for the member's avatar, or a placeholder div."""
    if member is None:
        return '<div class="avatar-placeholder">?</div>'

    url = member.display_avatar.url if hasattr(member, "display_avatar") else None
    if url:
        return f'<img src="{_esc(url)}" alt="{_esc(str(member))}" loading="lazy">'

    letter = (member.display_name or "?")[0].upper()
    return f'<div class="avatar-placeholder">{_esc(letter)}</div>'


def _message_html(msg: discord.Message) -> str:
    """Render a single discord.Message as an HTML block."""
    parts: list[str] = []

    author = msg.author
    name_html = f'<span class="username">{_esc(str(author))}</span>'
    if getattr(author, "bot", False):
        name_html += ' <span class="bot-badge">BOT</span>'

    ts_str = _ts(msg.created_at)
    header = (
        f'<div class="message-header">'
        f'{name_html}'
        f'<span class="timestamp">{_esc(ts_str)}</span>'
        f'</div>'
    )

    # Reply reference
    if msg.reference and msg.reference.resolved:
        ref = msg.reference.resolved
        ref_author = getattr(ref, "author", None)
        ref_name = str(ref_author) if ref_author else "Unknown"
        ref_content = (getattr(ref, "content", "") or "")[:80]
        parts.append(
            f'<div class="reply-preview">'
            f'<strong>{_esc(ref_name)}</strong>: {_esc(ref_content)}'
            f'</div>'
        )

    # Message content
    content = msg.content or ""
    if content:
        parts.append(f'<div class="message-content">{_esc(content)}</div>')
    elif not msg.attachments and not msg.embeds:
        parts.append('<div class="message-content" style="color:#80848e;font-style:italic;">[No content]</div>')

    # Attachments
    for att in msg.attachments:
        size_kb = att.size / 1024
        label = f"{att.filename} ({size_kb:.1f} KB)"
        parts.append(f'<div class="attachment">{_esc(label)}</div>')

    # Embeds (basic render)
    for emb in msg.embeds:
        embed_parts = []
        if emb.title:
            embed_parts.append(f'<div class="embed-title">{_esc(emb.title)}</div>')
        if emb.description:
            embed_parts.append(f'<div class="embed-description">{_esc(emb.description)}</div>')
        if embed_parts:
            colour_hex = str(emb.colour) if emb.colour else "#5865f2"
            border_style = f'border-left-color: {_esc(colour_hex)};'
            parts.append(
                f'<div class="embed-wrapper" style="{border_style}">'
                + "\n".join(embed_parts)
                + "</div>"
            )

    content_html = header + "\n".join(parts)

    avatar_html = _avatar_html(author)

    return (
        f'<div class="message-group">'
        f'<div class="avatar-col">{avatar_html}</div>'
        f'<div class="content-col">{content_html}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_html_transcript(
    messages: Sequence[discord.Message],
    *,
    channel_name: str = "deleted-messages",
    guild_name: str = "Unknown Server",
    extra_info: str = "",
) -> io.BytesIO:
    """
    Generate a self-contained dark-theme HTML transcript.

    Parameters
    ----------
    messages:
        The messages to include (should be ordered oldest → newest).
    channel_name:
        The source channel name shown in the header.
    guild_name:
        The guild name shown in the header.
    extra_info:
        Optional extra text shown in the header metadata area.

    Returns
    -------
    io.BytesIO
        A byte stream of the HTML file, ready to pass to ``discord.File``.
    """
    msg_count = min(len(messages), TRANSCRIPT_MAX_MESSAGES)
    display_messages = list(messages)[:msg_count]

    # Sort oldest → newest
    display_messages.sort(key=lambda m: m.created_at)

    now_str = datetime.now(tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    meta = f"{msg_count} messages · Generated {now_str}"
    if extra_info:
        meta = f"{extra_info} · {meta}"

    # Group messages by date for dividers
    message_blocks: list[str] = []
    last_date: str | None = None

    for msg in display_messages:
        msg_date = msg.created_at.strftime("%B %d, %Y")
        if msg_date != last_date:
            message_blocks.append(
                f'<div class="date-divider">{_esc(msg_date)}</div>'
            )
            last_date = msg_date
        message_blocks.append(_message_html(msg))

    messages_html = "\n".join(message_blocks)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript — #{_esc(channel_name)} · {_esc(guild_name)}</title>
    <style>{_CSS}</style>
</head>
<body>
<header>
    <span style="font-size:1.3rem;">💬</span>
    <span class="channel-name">#{_esc(channel_name)}</span>
    <span style="color:#949ba4;font-size:0.9rem;">{_esc(guild_name)}</span>
    <span class="meta">{_esc(meta)}</span>
</header>
<main class="messages-container">
    {messages_html}
</main>
<footer>
    TamozaLogger • Bulk Delete Transcript • {_esc(now_str)}
</footer>
</body>
</html>"""

    bio = io.BytesIO(html_doc.encode("utf-8"))
    bio.seek(0)
    return bio
