"""
cogs/help.py — Premium Interactive /help Slash Command
======================================================
Displays a clean, beautifully formatted, comprehensive directory
of all logging categories, forensic features, and administrative commands.

Automatically adapts to the server's configured language (Arabic 🇸🇦 / English 🇬🇧)
without requiring any command parameters.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database.db import db
from utils.embed_builder import build_embed, Colours

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embed Content Data (Arabic & English)
# ---------------------------------------------------------------------------

_HELP_DATA_AR = {
    "title": "🛡️ دليل نظام TamozaLogger — مركز العمليات والسجلات",
    "description": (
        "> **بوت يقوم بمتابعة جميع مايحدث بالخادم وتسجيلها والتحقق منها.**\n"
        "──────────────────────────────────────────"
    ),
    "fields": [
        (
            "💬 سجلات الرسائل والتفاعلات (`messages`)",
            "```yaml\n"
            "الأحداث: حذف الرسائل • تعديل الرسائل • الحذف الجماعي • التفاعلات • التاغات المخفية\n"
            "```\n"
            "• **🗑️ حذف الرسائل:** توثيق صاحب الرسالة، القناة، وتفاصيل المرفقات.\n"
            "• **✏️ تعديل الرسائل:** مقارنة فورية دقيقة للنص القديم والجديد مع رابط مباشر للرسالة.\n"
            "• **🧹 الحذف الجماعي (Purge):** إنشاء تقرير HTML تفاعلي متكامل مرفق مع السجل.\n"
            "• **⭐ التفاعلات:** تسجيل إضافة، إزالة، ومسح الريأكشنات بالكامل.\n"
            "• **⚠️ كشف الإشارات المخفية (Ghost Ping):** تنبيه عالي الأولوية عند منشن أعضاء وحذف الرسالة.",
            False,
        ),
        (
            "👥 سجلات الأعضاء والملفات الشخصية (`members`)",
            "```yaml\n"
            "الأحداث: دخول الأعضاء • خروج الأعضاء • تتبع الدعوات • الألقاب • الرتب • التايم آوت\n"
            "```\n"
            "• **🟢 دخول الأعضاء:** تنبيه الحسابات الجديدة وتتبع كود وصاحب رابط الدعوة (Invite Tracker).\n"
            "• **🔴 خروج الأعضاء:** حساب المدة الدقيقة للعضو بالسيرفر وتحديد أسباب المغادرة.\n"
            "• **👤 الألقاب والأسماء:** توثيق تغيرات الاسم المستعار وحفظها في الأرشيف.\n"
            "• **🏷️ الرتب والتحديثات:** توثيق الرتب المضافة والمزالة مع ذكر المشرف المسؤول.\n"
            "• **⏱️ التايم آوت:** تسجيل تطبيق، تمديد، أو إلغاء التايم آوت مع السبب والمدة.\n"
            "• **🖼️ الملف الشخصي:** تتبع تغييرات اسم المستخدم، الأفاتار، والبانر العام.",
            False,
        ),
        (
            "🔊 سجلات الرومات الصوتية والمسرح (`voice`)",
            "```yaml\n"
            "الأحداث: دخول • خروج • سحب قسري منفصل • انتقال شخصي • كتم • صمم • بث • كاميرا\n"
            "```\n"
            "• **🔀🔨 السحب والنقل القسري (منفصل):** تسجيل من قام بسحب العضو مع المشرف ورومات النقل.\n"
            "• **🔀 الانتقال العادي:** تسجيل تنقل العضو بنفسه بين الرومات الصوتية.\n"
            "• **🔴 الفصل القسري (ديسكونكت):** رصد وتوثيق عمليات طرد العضو من الروم الصوتي مع المشرف.\n"
            "• **🔊 دخول وخروج:** تسجيل أوقات الدخول والخروج وحساب مجموع ساعات الصوت.\n"
            "• **🎙️ الكتم والسماعة:** التفرقة الدقيقة بين الكتم الذاتي والكتم الإداري.\n"
            "• **📹 البث والكاميرا:** توثيق بدء وإيقاف مشاركة الشاشة وبث الكاميرا والمسرح.",
            False,
        ),
        (
            "📢 سجلات الرومات والأقسام والثردات (`channels`)",
            "```yaml\n"
            "الأحداث: إنشاء الرومات • حذف الرومات • تعديل الإعدادات • فروق الصلاحيات • الثردات\n"
            "```\n"
            "• **➕/➖ إنشاء وحذف:** رصد إنشاء وحذف الرومات النصية والصوتية والأقسام.\n"
            "• **📝 التعديلات:** تتبع تغيير الاسم، الوصف، وضع البطء (Slowmode)، وNSFW.\n"
            "• **🔐 الصلاحيات الدقيقة:** كشف تفصيلي لفروق الصلاحيات (`+سماح` ✅ / `-منع` ❌ / `~ضبط` ⬜).\n"
            "• **🧵 الثردات والمنتديات:** توثيق إنشاء، حذف، أرشفة، وإغلاق الثردات.",
            False,
        ),
        (
            "🏷️ سجلات الرتب والصلاحيات (`roles`)",
            "```yaml\n"
            "الأحداث: إنشاء الرتب • حذف الرتب • تعديل الرتب • الصلاحيات الحساسة • نسخ احتياطي\n"
            "```\n"
            "• **➕/➖ إنشاء وحذف:** رصد إنشاء وحذف الرتب مع تحديد المشرف المسؤول.\n"
            "• **📦 نسخة احتياطية:** حفظ قائمة الصلاحيات الكاملة للرتبة عند حذفها لاسترجاعها.\n"
            "• **🎨 التعديلات:** تتبع تغيير الاسم، اللون، التثبيت (Hoist)، والإشارة (Mentionable).\n"
            "• **⚠️ الصلاحيات الحساسة:** تنبيهات فورية عند منح صلاحيات الإدارة الحساسة (Admin/Ban/Manage).",
            False,
        ),
        (
            "⚙️ سجلات السيرفر والإشراف (`server` & `mod`)",
            "```yaml\n"
            "الأحداث: الحظر وفك الحظر • الطرد • الأوتومود • إعدادات السيرفر • الويب هوك • الإيموجيات\n"
            "```\n"
            "• **🔨 الحظر والطرد (Ban/Kick):** تسجيل عقوبات الباند والطرد مع اسم المشرف والسبب.\n"
            "• **🛡️ الأوتومود (AutoMod):** توثيق القواعد المحفزة، الكلمات المحظورة، والإجراء المتخذ.\n"
            "• **⚙️ إعدادات السيرفر:** رصد تغيير اسم السيرفر، الأيقونة، البانر، ومستوى الحماية.\n"
            "• **🔗 التكاملات:** تتبع إنشاء وحذف روابط الويب هوك (Webhooks)، الإيموجيات، والملصقات.",
            False,
        ),
        (
            "🛠️ أوامر الإدارة والتحكم",
            "```fix\n"
            "جميع الأوامر متاحة للمشرفين في كافة رومات السيرفر\n"
            "```\n"
            "• `/log set <log_type> <#channel>` — تعيين روم مخصص لحدث معين أو لقسم كامل.\n"
            "• `/log remove <log_type>` — إزالة روم السجل المخصص لحدث أو لقسم.\n"
            "• `/log clear` — مسح وإعادة تعيين كافة رومات السجلات في السيرفر.\n"
            "• `/log status` — عرض تقرير شامل بجميع الرومات المربوطة وقوائم الاستثناءات.\n"
            "• `/log ignore add/remove <type> <target>` — استثناء روم أو رتبة أو عضو من السجلات.\n"
            "• `/whois <user>` — تقرير أمني وجنائي مفصل وشامل للعضو في رسالة واحدة.\n"
            "• `/language <language>` — تغيير لغة البوت (العربية 🇸🇦 / English 🇬🇧).\n"
            "• `/about` — معلومات عن البوت والمطور (Tamoza.net).\n"
            "• `/help` — عرض هذا الدليل التعريفي الشامل.",
            False,
        ),
    ],
}

_HELP_DATA_EN = {
    "title": "🛡️ TamozaLogger System Guide — Operations & Forensics",
    "description": (
        "> **An advanced enterprise bot that monitors, logs, and verifies everything happening in the server.**\n"
        "──────────────────────────────────────────"
    ),
    "fields": [
        (
            "💬 Message Logs & Interactions (`messages`)",
            "```yaml\n"
            "Events: Deletions • Edits • Purges • Reactions • Ghost Pings\n"
            "```\n"
            "• **🗑️ Deletions:** Logs author, channel, creation time, attachments & sizes.\n"
            "• **✏️ Edits:** Side-by-side inline text diff with direct jump link.\n"
            "• **🧹 Bulk Purges:** Generates a standalone interactive HTML Discord transcript.\n"
            "• **⭐ Reactions:** Tracks reaction adds, removals, and emoji clears.\n"
            "• **⚠️ Ghost Pings:** High-priority alerts flagging user/role mentions in deleted messages.",
            False,
        ),
        (
            "👥 Member & Profile Logs (`members`)",
            "```yaml\n"
            "Events: Joins • Leaves • Invite Tracking • Nicknames • Roles • Timeouts\n"
            "```\n"
            "• **🟢 Joins:** New account age warnings + native invite code and inviter attribution.\n"
            "• **🔴 Leaves:** Exact time spent in server + kick/leave classification.\n"
            "• **👤 Nicknames:** Before vs after comparison with persistent history archive.\n"
            "• **🏷️ Roles:** Added and removed roles with audit log moderator attribution.\n"
            "• **⏱️ Timeouts:** Applied, extended, or removed with duration and reason.\n"
            "• **🖼️ Profiles:** Global username, avatar, and banner change tracking.",
            False,
        ),
        (
            "🔊 Voice & Stage Logs (`voice`)",
            "```yaml\n"
            "Events: Join • Leave • Force Move (Separate) • Self Switch • Disconnect • Media\n"
            "```\n"
            "• **🔀🔨 Force Move (Separate):** Dedicated log for moderator drags with actor attribution.\n"
            "• **🔀 Voice Switch:** Tracks self-initiated channel switching.\n"
            "• **🔴 Force Disconnect:** Classifies moderator disconnects vs self-leaves.\n"
            "• **🔊 Join / Leave:** Tracks time-in-channel and cumulative voice duration.\n"
            "• **🎙️ Mute & Deafen:** Differentiates self-mute/deaf from server-wide mod actions.\n"
            "• **📹 Screen Share & Cam:** Tracks live stream and video toggle events.",
            False,
        ),
        (
            "📢 Channel & Thread Logs (`channels`)",
            "```yaml\n"
            "Events: Channel Create • Delete • Settings • Permission Overwrites • Threads\n"
            "```\n"
            "• **➕/➖ Create & Delete:** Tracks text, voice, stage channels, and categories.\n"
            "• **📝 Updates:** Name, Topic, Slowmode rate limit, NSFW, Bitrate changes.\n"
            "• **🔐 Permission Overwrites:** Granular diffs (`+Allow` ✅ / `-Deny` ❌ / `~Reset` ⬜).\n"
            "• **🧵 Threads & Forums:** Creation, deletion, archiving, and locking.",
            False,
        ),
        (
            "🏷️ Role & Permission Logs (`roles`)",
            "```yaml\n"
            "Events: Role Create • Delete • Updates • Sensitive Perms • Perm Backup\n"
            "```\n"
            "• **➕/➖ Create & Delete:** Role lifecycle with audit log executor attribution.\n"
            "• **📦 Permission Backup:** Complete permissions list saved as code block on deletion.\n"
            "• **🎨 Updates:** Name, Colour hex, Hoist, Mentionable, and Icon changes.\n"
            "• **⚠️ Sensitive Perms:** Alerts on high-risk permission grants (Admin, Ban, Manage).",
            False,
        ),
        (
            "⚙️ Server & Moderation Logs (`server` & `mod`)",
            "```yaml\n"
            "Events: Bans • Kicks • AutoMod • Server Settings • Webhooks • Emojis\n"
            "```\n"
            "• **🔨 Bans & Kicks:** Mod-attributed punishments with reason.\n"
            "• **🛡️ AutoMod:** Rule name, matched keyword/regex, action taken.\n"
            "• **⚙️ Server Settings:** Server name, icon, banner, verification level, system channel.\n"
            "• **🔗 Integrations:** Webhook CRUD, custom Emojis, and Stickers.",
            False,
        ),
        (
            "🛠️ Admin & Control Commands",
            "```fix\n"
            "All commands are available to server administrators in any channel\n"
            "```\n"
            "• `/log set <log_type> <#channel>` — Route a specific event or general category.\n"
            "• `/log remove <log_type>` — Remove a configured log channel mapping.\n"
            "• `/log clear` — Clear all configured log channels.\n"
            "• `/log status` — Comprehensive overview of all active mappings & ignore list.\n"
            "• `/log ignore add/remove <type> <target>` — Ignore channel/role/user from logging.\n"
            "• `/whois <user>` — Full single-message user forensics and risk report.\n"
            "• `/language <language>` — Switch server bot language (English 🇬🇧 / Arabic 🇸🇦).\n"
            "• `/about` — Information about the bot and developer (Tamoza.net).\n"
            "• `/help` — Display this comprehensive help directory.",
            False,
        ),
    ],
}


def build_help_embed(lang: str, requester: str) -> discord.Embed:
    """Construct a clean, high-visual-appeal help embed."""
    data = _HELP_DATA_AR if lang == "ar" else _HELP_DATA_EN
    now = datetime.now(tz=timezone.utc)

    footer = (
        f"المستدعي: {requester} • TamozaLogger"
        if lang == "ar"
        else f"Requested by {requester} • TamozaLogger"
    )

    return build_embed(
        event_type="neutral",
        title=data["title"],
        description=data["description"],
        colour=Colours.SERVER,
        fields=data["fields"],
        footer_text=footer,
        timestamp=now,
    )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Help(commands.Cog, name="Help"):
    """Help and system capabilities command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="help",
        description="عرض دليل الأوامر والسجلات والخدمات / Display system help directory",
    )
    async def help_command(self, interaction: discord.Interaction) -> None:
        """Render the system help embed in the server's configured language."""
        await interaction.response.defer(ephemeral=False)

        guild_id = interaction.guild_id or 0
        lang = await db.get_guild_language(guild_id) if guild_id else "ar"

        embed = build_help_embed(lang, str(interaction.user))
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="about",
        description="معلومات عن البوت والمطور / Information about the bot and developer",
    )
    async def about_command(self, interaction: discord.Interaction) -> None:
        """Display information about TamozaLogger and its creator."""
        await interaction.response.defer(ephemeral=False)
        guild_id = interaction.guild_id or 0
        lang = await db.get_guild_language(guild_id) if guild_id else "ar"

        bot_user = self.bot.user
        avatar_url = bot_user.display_avatar.url if bot_user else None
        latency_ms = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)

        if lang == "ar":
            title = "🛡️ حول نظام TamozaLogger"
            description = (
                "**بوت متطور وشامل لمتابعة وتوثيق جميع ما يحدث في الخادم وتسجيلها والتحقق منها.**\n\n"
                "> 🌐 **تم تطوير هذا البوت بواسطة: [Tamoza.net](https://tamoza.net)**\n"
                "> 🌐 **This bot Created by [Tamoza.net](https://tamoza.net)**"
            )
            fields = [
                ("👑 المطور والمنشئ", "[Tamoza.net](https://tamoza.net)", True),
                ("⚡ سرعة الاستجابة", f"`{latency_ms}ms`", True),
                ("🌐 عدد السيرفرات", f"`{guild_count}`", True),
                (
                    "🛡️ المميزات الرئيسية",
                    "• توثيق تفصيلي فوري لكافة الأحداث الصوتية والنصية.\n"
                    "• فصل السحب القسري (`Force Move`) والديسكونكت بدقة.\n"
                    "• كشف التاغات المخفية (`Ghost Ping`) وتتبع الدعوات.\n"
                    "• تقارير أمنية وجنائية متكاملة عبر `/whois`.\n"
                    "• دعم كامل للغتين العربية 🇸🇦 والإنجليزية 🇬🇧.",
                    False,
                ),
            ]
            footer = "TamozaLogger • تم التطوير بواسطة Tamoza.net"
        else:
            title = "🛡️ About TamozaLogger"
            description = (
                "**An advanced enterprise Discord bot that monitors, logs, and verifies everything happening in the server.**\n\n"
                "> 🌐 **This bot Created by [Tamoza.net](https://tamoza.net)**"
            )
            fields = [
                ("👑 Developer", "[Tamoza.net](https://tamoza.net)", True),
                ("⚡ Latency", f"`{latency_ms}ms`", True),
                ("🌐 Servers", f"`{guild_count}`", True),
                (
                    "🛡️ Key Features",
                    "• Granular logging for all voice and message events.\n"
                    "• Precise moderator attribution for Force Moves & Disconnects.\n"
                    "• Ghost ping detection and native invite tracking.\n"
                    "• Complete user forensics and safety score with `/whois`.\n"
                    "• Full bilingual support (English 🇬🇧 & Arabic 🇸🇦).",
                    False,
                ),
            ]
            footer = "TamozaLogger • Created by Tamoza.net"

        embed = build_embed(
            event_type="neutral",
            title=title,
            description=description,
            colour=Colours.SERVER,
            fields=fields,
            thumbnail_url=avatar_url,
            footer_text=footer,
            timestamp=datetime.now(tz=timezone.utc),
        )

        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Tamoza.net",
                url="https://tamoza.net",
                style=discord.ButtonStyle.link,
                emoji="🌐",
            )
        )

        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
