"""
config.py — TamozaLogger Central Configuration
===============================================
All configuration is read from environment variables (via .env file).
Copy .env.example → .env and fill in your values before running.
"""

from __future__ import annotations

import os
from typing import Final

from dotenv import load_dotenv

# Load .env file from the project root (if present)
load_dotenv()


# ---------------------------------------------------------------------------
# Bot credentials
# ---------------------------------------------------------------------------

#: Your Discord bot token from the Developer Portal.
BOT_TOKEN: Final[str] = os.environ["BOT_TOKEN"]

#: asyncpg-compatible PostgreSQL DSN.
#: Format: postgresql://user:password@host:port/dbname
DB_DSN: Final[str] = os.environ["DB_DSN"]


# ---------------------------------------------------------------------------
# Bot behaviour
# ---------------------------------------------------------------------------

#: Default command prefix used when slash commands are unavailable.
DEFAULT_PREFIX: Final[str] = os.getenv("DEFAULT_PREFIX", "!")

#: The application/client ID of the bot (used for invite link generation).
APPLICATION_ID: Final[int] = int(os.getenv("APPLICATION_ID", "0"))

#: Optional single guild ID to sync slash commands to instantly (dev mode).
#: Leave empty ("") to sync globally (takes up to 1 hour).
DEV_GUILD_ID: Final[int | None] = (
    int(os.environ["DEV_GUILD_ID"]) if os.getenv("DEV_GUILD_ID") else None
)


# ---------------------------------------------------------------------------
# Logging categories & granular event types (used as DB keys for log_channels)
# ---------------------------------------------------------------------------

LOG_CATEGORIES: Final[list[str]] = [
    "messages",   # Message edits, deletes, bulk purge, reactions
    "members",    # Join, leave, nick/role/timeout changes, profile updates
    "voice",      # VC join/leave/move, mute, deafen, stream, stage
    "channels",   # Channel/thread CRUD and permission changes
    "roles",      # Role CRUD and permission changes
    "server",     # Guild updates, webhooks, emoji, stickers, soundboard
    "mod",        # Bans, kicks, unbans, AutoMod actions
]

LOG_EVENT_TYPES: Final[dict[str, dict[str, Any]]] = {
    # ── سجلات الأعضاء (Member Events) ──
    "member_join": {
        "name_en": "🟢 Member Join (New members)",
        "name_ar": "🟢 دخول الأعضاء الجدد",
        "category": "members",
    },
    "member_leave": {
        "name_en": "🔴 Member Leave (Members who left)",
        "name_ar": "🔴 خروج ومغادرة الأعضاء",
        "category": "members",
    },
    "member_kick": {
        "name_en": "👢 Member Kick",
        "name_ar": "👢 طرد الأعضاء (كيك)",
        "category": "mod",
    },
    "member_update": {
        "name_en": "👤 Member Update (Nicknames, roles)",
        "name_ar": "👤 تعديل الأعضاء (ألقاب ورتب)",
        "category": "members",
    },
    "user_update": {
        "name_en": "🖼️ Profile Update (Avatar, username)",
        "name_ar": "🖼️ تحديث الملف الشخصي للعضو",
        "category": "members",
    },

    # ── سجلات الصوت (Voice Events) ──
    "voice_join": {
        "name_en": "🔊 Voice Join",
        "name_ar": "🔊 دخول الروم الصوتي",
        "category": "voice",
    },
    "voice_leave": {
        "name_en": "🔇 Voice Leave",
        "name_ar": "🔇 خروج من الروم الصوتي",
        "category": "voice",
    },
    "voice_force_move": {
        "name_en": "🔀🔨 Force Moved (by Moderator)",
        "name_ar": "🔀🔨 سحب ونقل قسري (بواسطة مشرف)",
        "category": "voice",
    },
    "voice_move": {
        "name_en": "🔀 Voice Switch (Self-moved)",
        "name_ar": "🔀 انتقال بين الرومات (شخصي)",
        "category": "voice",
    },
    "voice_disconnect": {
        "name_en": "🔴 Voice Disconnect (Forced disconnect)",
        "name_ar": "🔴 فصل قسري من الروم (ديسكونكت)",
        "category": "voice",
    },
    "voice_state": {
        "name_en": "🎙️ Voice State (Mute, deaf, stream, cam)",
        "name_ar": "🎙️ حالة الصوت (كتم، صمم، بث، كاميرا)",
        "category": "voice",
    },

    # ── سجلات الرسائل (Message Events) ──
    "message_delete": {
        "name_en": "🗑️ Message Delete",
        "name_ar": "🗑️ حذف الرسائل",
        "category": "messages",
    },
    "message_edit": {
        "name_en": "✏️ Message Edit",
        "name_ar": "✏️ تعديل الرسائل",
        "category": "messages",
    },
    "message_purge": {
        "name_en": "🧹 Bulk Delete (Purge)",
        "name_ar": "🧹 حذف جماعي للرسائل",
        "category": "messages",
    },
    "reactions": {
        "name_en": "⭐ Message Reactions",
        "name_ar": "⭐ تفاعلات الرسائل",
        "category": "messages",
    },

    # ── سجلات الإشراف والعقوبات (Moderation Events) ──
    "member_ban": {
        "name_en": "🔨 Member Ban / Unban",
        "name_ar": "🔨 حظر وفك حظر الأعضاء",
        "category": "mod",
    },
    "member_timeout": {
        "name_en": "⏱️ Member Timeout",
        "name_ar": "⏱️ عقوبات التايم آوت",
        "category": "mod",
    },
    "automod": {
        "name_en": "🛡️ AutoMod Actions",
        "name_ar": "🛡️ إجراءات الأوتومود",
        "category": "mod",
    },

    # ── سجلات الرومات (Channel Events) ──
    "channel_create": {
        "name_en": "➕ Channel Create",
        "name_ar": "➕ إنشاء الرومات",
        "category": "channels",
    },
    "channel_delete": {
        "name_en": "➖ Channel Delete",
        "name_ar": "➖ حذف الرومات",
        "category": "channels",
    },
    "channel_update": {
        "name_en": "📝 Channel & Thread Update",
        "name_ar": "📝 تعديل الرومات والثريدات",
        "category": "channels",
    },

    # ── سجلات الرتب (Role Events) ──
    "role_create": {
        "name_en": "➕ Role Create",
        "name_ar": "➕ إنشاء الرتب",
        "category": "roles",
    },
    "role_delete": {
        "name_en": "➖ Role Delete",
        "name_ar": "➖ حذف الرتب",
        "category": "roles",
    },
    "role_update": {
        "name_en": "📝 Role & Perms Update",
        "name_ar": "📝 تعديل الرتب والصلاحيات",
        "category": "roles",
    },

    # ── سجلات السيرفر (Server Events) ──
    "server_update": {
        "name_en": "⚙️ Server Update",
        "name_ar": "⚙️ تعديل إعدادات السيرفر",
        "category": "server",
    },
    "emoji_update": {
        "name_en": "😀 Emoji & Sticker Changes",
        "name_ar": "😀 تعديل الإيموجيات والملصقات",
        "category": "server",
    },
    "webhook_update": {
        "name_en": "🔗 Webhook Changes",
        "name_ar": "🔗 تعديل الويب هوك",
        "category": "server",
    },

    # ── الأقسام الشاملة (General Categories) ──
    "members": {
        "name_en": "👥 All Member Logs (General)",
        "name_ar": "👥 جميع سجلات الأعضاء (شامل)",
        "category": None,
    },
    "voice": {
        "name_en": "🎙️ All Voice Logs (General)",
        "name_ar": "🎙️ جميع سجلات الصوت (شامل)",
        "category": None,
    },
    "messages": {
        "name_en": "💬 All Message Logs (General)",
        "name_ar": "💬 جميع سجلات الرسائل (شامل)",
        "category": None,
    },
    "channels": {
        "name_en": "📁 All Channel Logs (General)",
        "name_ar": "📁 جميع سجلات الرومات (شامل)",
        "category": None,
    },
    "roles": {
        "name_en": "🛡️ All Role Logs (General)",
        "name_ar": "🛡️ جميع سجلات الرتب (شامل)",
        "category": None,
    },
    "server": {
        "name_en": "⚙️ All Server Logs (General)",
        "name_ar": "⚙️ جميع سجلات السيرفر (شامل)",
        "category": None,
    },
    "mod": {
        "name_en": "⚖️ All Moderation Logs (General)",
        "name_ar": "⚖️ جميع سجلات الإشراف (شامل)",
        "category": None,
    },
}


# ---------------------------------------------------------------------------
# Embed colour palette (integer values for discord.Colour)
# ---------------------------------------------------------------------------

class Colours:
    """Centralised colour palette for all log embeds."""
    CREATE     = 0x2ECC71   # Green  — joins, creates
    DELETE     = 0xE74C3C   # Red    — leaves, deletes, bans
    UPDATE     = 0xF39C12   # Orange — edits, updates
    VOICE      = 0x3498DB   # Blue   — voice events
    TIMEOUT    = 0xE67E22   # Amber  — timeouts
    MOD        = 0x9B59B6   # Purple — mod actions
    SERVER     = 0x1ABC9C   # Teal   — server/guild events
    WARN       = 0xFF6B6B   # Bright red — ghost pings, new account warnings
    NEUTRAL    = 0x95A5A6   # Grey   — misc / neutral


# ---------------------------------------------------------------------------
# Audit log fetcher tuning
# ---------------------------------------------------------------------------

#: Seconds to wait before querying the Audit Log to allow propagation.
AUDIT_LOG_DELAY: Final[float] = float(os.getenv("AUDIT_LOG_DELAY", "0.75"))

#: Maximum seconds an audit log entry can be old to be considered a match.
AUDIT_LOG_WINDOW: Final[float] = float(os.getenv("AUDIT_LOG_WINDOW", "5.0"))

#: How many audit log entries to fetch per query.
AUDIT_LOG_LIMIT: Final[int] = int(os.getenv("AUDIT_LOG_LIMIT", "5"))


# ---------------------------------------------------------------------------
# Transcript generator
# ---------------------------------------------------------------------------

#: Maximum number of messages to include in a single bulk-delete transcript.
TRANSCRIPT_MAX_MESSAGES: Final[int] = int(os.getenv("TRANSCRIPT_MAX_MESSAGES", "1000"))
