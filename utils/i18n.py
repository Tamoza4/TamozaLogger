"""
utils/i18n.py — Global Log Localization & Internationalization Engine
======================================================================
Provides translation mappings for all log events across all cogs.
Supports English ('en') and Arabic ('ar').
"""

from __future__ import annotations

from typing import Any

# Translation dictionary
_STRINGS = {
    # ── General & Common ──────────────────────────────────────────────
    "user": {"en": "User", "ar": "العضو"},
    "member": {"en": "Member", "ar": "العضو"},
    "channel": {"en": "Channel", "ar": "الروم"},
    "by": {"en": "By", "ar": "بواسطة"},
    "updated_by": {"en": "Updated By", "ar": "عدل بواسطة"},
    "created_by": {"en": "Created By", "ar": "أنشئ بواسطة"},
    "deleted_by": {"en": "Deleted By", "ar": "حذف بواسطة"},
    "kicked_by": {"en": "Kicked By", "ar": "طرد بواسطة"},
    "banned_by": {"en": "Banned By", "ar": "حظر بواسطة"},
    "unbanned_by": {"en": "Unbanned By", "ar": "فك الحظر بواسطة"},
    "reason": {"en": "Reason", "ar": "السبب"},
    "no_reason": {"en": "No reason provided", "ar": "لم يتم تقديم سبب"},
    "user_id": {"en": "User ID", "ar": "معرف العضو"},
    "message_id": {"en": "Message ID", "ar": "معرف الرسالة"},
    "role_id": {"en": "Role ID", "ar": "معرف الرتبة"},
    "channel_id": {"en": "Channel ID", "ar": "معرف الروم"},

    # ── Message Logs ──────────────────────────────────────────────────
    "ghost_ping_title": {"en": "👻 Ghost Ping Detected!", "ar": "👻 تم كشف إشارة مخفية (Ghost Ping)!"},
    "ghost_ping_desc": {
        "en": "**{author}** pinged targets in {channel} then deleted the message.\n\n**Pinged Targets:**\n{targets}",
        "ar": "قام **{author}** بالإشارة إلى أعضاء/رتب في {channel} ثم قام بحذف الرسالة.\n\n**الأهداف المشار إليها:**\n{targets}",
    },
    "msg_deleted_title": {"en": "🗑️ Message Deleted", "ar": "🗑️ تم حذف رسالة"},
    "content": {"en": "Content", "ar": "المحتوى"},
    "lifespan": {"en": "Lifespan", "ar": "عمر الرسالة"},
    "sent_at": {"en": "Sent At", "ar": "وقت الإرسال"},
    "reply_to": {"en": "Reply To", "ar": "رد على"},
    "attachments": {"en": "Attachments", "ar": "المرفقات"},
    "msg_edited_title": {"en": "✏️ Message Edited", "ar": "✏️ تم تعديل رسالة"},
    "jump": {"en": "Jump", "ar": "انتقال"},
    "before": {"en": "Before", "ar": "قبل التعديل"},
    "after": {"en": "After", "ar": "بعد التعديل"},
    "diff": {"en": "Diff", "ar": "الفروقات"},
    "bulk_delete_title": {"en": "🧹 Bulk Message Delete — {count} Messages", "ar": "🧹 حذف جماعي — {count} رسالة"},
    "bulk_delete_desc": {
        "en": "**{count}** messages were bulk-deleted in {channel}.",
        "ar": "تم حذف **{count}** رسالة بشكل جماعي في {channel}.",
    },
    "transcript_attached": {"en": "📄 **HTML Transcript attached below.**", "ar": "📄 **تم إرفاق سجل الحذف التفاعلي بالأسفل.**"},
    "msg_count": {"en": "Message Count", "ar": "عدد الرسائل"},
    "reaction_added": {"en": "⭐ Reaction Added", "ar": "⭐ تم إضافة تفاعل"},
    "reaction_removed": {"en": "💔 Reaction Removed", "ar": "💔 تم إزالة تفاعل"},
    "reactions_cleared": {"en": "🧹 All Reactions Cleared", "ar": "🧹 تم مسح جميع التفاعلات"},

    # ── Member Logs ───────────────────────────────────────────────────
    "member_joined_title": {"en": "📥 Member Joined", "ar": "📥 انضمام عضو جديد"},
    "account_age": {"en": "Account Age", "ar": "عمر الحساب"},
    "join_pos": {"en": "Join Position", "ar": "ترتيب الانضمام"},
    "joined_at": {"en": "Joined At", "ar": "تاريخ الانضمام"},
    "invite_used": {"en": "Invite Used", "ar": "رابط الدعوة المستخدم"},
    "invited_by": {"en": "Code `{code}` — Invited by {inviter}", "ar": "الرمز `{code}` — تمت الدعوة بواسطة {inviter}"},
    "invite_unknown": {"en": "Could not determine (vanity/bot/DM invite)", "ar": "لم يتم التحديد (رابط خاص/بوت/دعوة مباشرة)"},
    "member_left_title": {"en": "📤 Member Left", "ar": "📤 مغادرة عضو"},
    "member_kicked_title": {"en": "👢 Member Kicked", "ar": "👢 تم طرد عضو"},
    "time_in_server": {"en": "Time In Server", "ar": "المدة في السيرفر"},
    "roles": {"en": "Roles", "ar": "الرتب"},
    "nick_changed_title": {"en": "📝 Nickname Changed", "ar": "📝 تم تغيير الاسم المستعار"},
    "prev_nick": {"en": "Previous Nick", "ar": "الاسم السابق"},
    "new_nick": {"en": "New Nick", "ar": "الاسم الجديد"},
    "roles_updated_title": {"en": "🏷️ Member Roles Updated", "ar": "🏷️ تم تحديث رتب العضو"},
    "roles_added": {"en": "Roles Added", "ar": "الرتب المضافة"},
    "roles_removed": {"en": "Roles Removed", "ar": "الرتب المزالة"},
    "timeout_applied": {"en": "⏱️ Member Timed Out", "ar": "⏱️ تم تطبيق تايم آوت على عضو"},
    "timeout_extended": {"en": "⏱️ Timeout Extended", "ar": "⏱️ تم تمديد التايم آوت"},
    "timeout_removed": {"en": "✅ Timeout Removed", "ar": "✅ تم إزالة التايم آوت"},
    "duration": {"en": "Duration", "ar": "المدة"},
    "expires_at": {"en": "Expires At", "ar": "تاريخ الانتهاء"},
    "profile_updated_title": {"en": "🖼️ User Profile Updated", "ar": "🖼️ تم تحديث الملف الشخصي"},

    # ── Voice Logs ────────────────────────────────────────────────────
    "vc_joined": {"en": "🟢 Joined Voice Channel", "ar": "🟢 دخول روم صوتي"},
    "vc_left": {"en": "🔴 Left Voice Channel", "ar": "🔴 خروج من روم صوتي"},
    "vc_moved": {"en": "🔀 Moved Voice Channel", "ar": "🔀 انتقال بين رومات صوتية"},
    "from": {"en": "From", "ar": "من"},
    "to": {"en": "To", "ar": "إلى"},
    "server_muted": {"en": "🔇 Server Muted", "ar": "🔇 كتم إداري"},
    "server_unmuted": {"en": "🔊 Server Unmuted", "ar": "🔊 إلغاء الكتم الإداري"},
    "server_deafened": {"en": "🔕 Server Deafened", "ar": "🔕 صمم إداري"},
    "server_undeafened": {"en": "🔔 Server Undeafened", "ar": "🔔 إلغاء الصمم الإداري"},
    "mic_muted": {"en": "🙊 Microphone Muted", "ar": "🙊 تم كتم الميكروفون"},
    "mic_unmuted": {"en": "🎤 Microphone Unmuted", "ar": "🎤 تم تفعيل الميكروفون"},
    "headset_off": {"en": "🙉 Headphones Off (Deafened)", "ar": "<ctrl42> تم إيقاف السماعة"},
    "headset_on": {"en": "🎧 Headphones On (Undeafened)", "ar": "🎧 تم تفعيل السماعة"},
    "stream_start": {"en": "📺 Screen Share Started", "ar": "📺 بدء مشاركة الشاشة"},
    "stream_stop": {"en": "📺 Screen Share Ended", "ar": "📺 إنهاء مشاركة الشاشة"},
    "cam_on": {"en": "📷 Camera Enabled", "ar": "📷 تشغيل الكاميرا"},
    "cam_off": {"en": "📷 Camera Disabled", "ar": "📷 إيقاف الكاميرا"},

    # ── Channel Logs ──────────────────────────────────────────────────
    "channel_created": {"en": "📢 Channel Created", "ar": "📢 تم إنشاء روم"},
    "channel_deleted": {"en": "🗑️ Channel Deleted", "ar": "🗑️ تم حذف روم"},
    "channel_updated": {"en": "✏️ Channel Updated", "ar": "✏️ تم تحديث روم"},
    "name": {"en": "Name", "ar": "الاسم"},
    "type": {"en": "Type", "ar": "النوع"},
    "category": {"en": "Category", "ar": "القسم"},
    "slowmode": {"en": "Slowmode", "ar": "وضع البطء"},
    "nsfw": {"en": "NSFW", "ar": "المحتوى الحساس (NSFW)"},
    "bitrate": {"en": "Bitrate", "ar": "جودة الصوت (Bitrate)"},
    "perm_overwrite_title": {"en": "🔐 Permission Overwrite Changed", "ar": "🔐 تم تغيير صلاحيات الروم"},
    "target": {"en": "Target", "ar": "الهدف"},
    "changes": {"en": "Changes", "ar": "التغييرات"},

    # ── Role Logs ─────────────────────────────────────────────────────
    "role_created": {"en": "✅ Role Created", "ar": "✅ تم إنشاء رتبة"},
    "role_deleted": {"en": "🗑️ Role Deleted", "ar": "🗑️ تم حذف رتبة"},
    "role_updated": {"en": "✏️ Role Updated", "ar": "✏️ تم تحديث رتبة"},
    "colour": {"en": "Colour", "ar": "اللون"},
    "hoisted": {"en": "Hoisted", "ar": "مثبتة (Hoist)"},
    "mentionable": {"en": "Mentionable", "ar": "قابلية الإشارة (Mentionable)"},
    "position": {"en": "Position", "ar": "الترتيب"},
    "perms_backup": {"en": "Permissions (Backup)", "ar": "الصلاحيات (نسخة احتياطية)"},
    "perm_changes": {"en": "Permission Changes", "ar": "تغييرات الصلاحيات"},
    "sensitive_perms": {"en": "⚠️ Sensitive Permissions Changed", "ar": "⚠️ تغييرات في صلاحيات حساسة"},

    # ── Server Logs ───────────────────────────────────────────────────
    "member_banned_title": {"en": "🔨 Member Banned", "ar": "🔨 تم حظر عضو (Ban)"},
    "member_unbanned_title": {"en": "🕊️ Member Unbanned", "ar": "🕊️ تم فك حظر عضو (Unban)"},
    "automod_action_title": {"en": "🤖 AutoMod Action", "ar": "🤖 إجراء الحماية التلقائية (AutoMod)"},
    "rule": {"en": "Rule", "ar": "القاعدة"},
    "action": {"en": "Action", "ar": "الإجراء"},
    "matched_content": {"en": "Matched Content", "ar": "المحتوى المطابق"},
    "matched_keyword": {"en": "Matched Keyword", "ar": "الكلمة الدليليّة"},
    "guild_updated_title": {"en": "⚙️ Server Settings Updated", "ar": "⚙️ تم تحديث إعدادات السيرفر"},
    "webhook_created": {"en": "🔗 Webhook Created", "ar": "🔗 تم إنشاء ويب هوك"},
    "webhook_updated": {"en": "🔗 Webhook Updated", "ar": "🔗 تم تحديث ويب هوك"},
    "webhook_deleted": {"en": "🔗 Webhook Deleted", "ar": "🔗 تم حذف ويب هوك"},
    "emoji_added": {"en": "😀 Emoji Added", "ar": "😀 تم إضافة إيموجي"},
    "emoji_removed": {"en": "😢 Emoji Removed", "ar": "😢 تم إزالة إيموجي"},
    "sticker_added": {"en": "🎨 Sticker Added", "ar": "🎨 تم إضافة ستيكر"},
    "sticker_removed": {"en": "🗑️ Sticker Removed", "ar": "🗑️ تم إزالة ستيكر"},
}


def t(key: str, lang: str = "en", **kwargs: Any) -> str:
    """
    Get a localized string by key and language code ('en' or 'ar').
    Supports optional format placeholders.
    """
    entry = _STRINGS.get(key, {})
    template = entry.get(lang) or entry.get("en") or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
