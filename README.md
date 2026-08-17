# 🔍 TamozaLogger

**Enterprise-grade Discord Logging & Forensics Bot** — fully standalone, zero external APIs, built on `discord.py` v2.x + `asyncpg` + PostgreSQL.

---

## ✨ Features

| Category | Events Tracked |
|---|---|
| **Messages** | Delete (ghost ping detection), edit diff, bulk purge → HTML transcript, reactions |
| **Members** | Join (invite tracker, account age warning), leave (duration), kick detection, nick/role/timeout changes, global profile updates |
| **Voice** | Join/leave/move (session timer), server mute/deafen (mod attribution), self mute/deafen, screen share, camera, stage transitions |
| **Channels** | Create/delete/update (name, topic, slowmode, NSFW, bitrate), permission overwrite diffs, thread lifecycle |
| **Roles** | Create/delete (permissions backup), update (colour, hoist, mentionable, icon, permission bitfield diff, sensitive perm alerts) |
| **Server** | Guild setting changes, webhooks CRUD, emoji/sticker add/remove, AutoMod execution & rule changes |
| **Mod** | Bans, unbans, kicks — all with executor + reason from audit log |

---

## 🗂️ Project Structure

```
discord_logger_bot/
├── bot.py                          # Entry point
├── config.py                       # Configuration (reads .env)
├── requirements.txt
├── .env.example
├── cogs/
│   ├── settings.py                 # /log set | /log ignore | /log status
│   ├── message_logs.py
│   ├── member_logs.py
│   ├── voice_logs.py
│   ├── channel_logs.py
│   ├── role_logs.py
│   └── server_logs.py
├── utils/
│   ├── audit_matcher.py            # Delayed audit log fetcher
│   ├── embed_builder.py            # Centralised embed factory
│   ├── permissions_diff.py         # Permission bitfield diff engine
│   └── transcript_generator.py     # Self-contained HTML transcript
└── database/
    ├── db.py                       # asyncpg pool + CRUD helpers
    └── schema.sql                  # PostgreSQL DDL
```

---

## ⚡ Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- A Discord bot with the following enabled in the [Developer Portal](https://discord.com/developers/applications):
  - ✅ **Server Members Intent**
  - ✅ **Message Content Intent**
  - ✅ **Presence Intent** *(optional)*

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in BOT_TOKEN and DB_DSN
```

### 4. Apply the database schema

```bash
psql -U your_user -d your_database -f database/schema.sql
```

### 5. Run the bot

```bash
python bot.py
```

---

## ⚙️ Configuration Commands

All commands require **Manage Server** permission.

| Command | Description |
|---|---|
| `/log set <category> <channel>` | Route a log category to a specific text channel |
| `/log ignore add <type> <target>` | Add a channel/role/user to the ignore list |
| `/log ignore remove <type> <target>` | Remove from the ignore list |
| `/log status` | View current routing and ignore list |
| `/log prefix <new_prefix>` | Change the text command prefix |

### Log Categories

| Value | What it logs |
|---|---|
| `messages` | Message edits, deletes, purges, reactions |
| `members` | Joins, leaves, nick/role/timeout changes |
| `voice` | Voice channel events |
| `channels` | Channel and thread events |
| `roles` | Role creation, deletion, updates |
| `server` | Guild-level events, webhooks, emojis |
| `mod` | Bans, kicks, unbans, timeouts, AutoMod |

---

## 🏗️ Architecture Highlights

### Audit Log Matching
`utils/audit_matcher.py` implements a **delayed async fetcher** that:
1. Waits `0.75s` (configurable) for Discord's API propagation
2. Scans the latest `N` entries for the target action
3. Filters by target ID and a `5s` recency window
4. Returns `(executor, reason)` or `(None, None)` on miss

### Invite Tracker
On every member join, the bot compares the **live invite uses** against the **cached snapshot in PostgreSQL** to identify which invite was used — works with all invite types except vanity URLs (which are detected separately).

### HTML Transcripts
Bulk deletes generate a **fully self-contained dark-theme HTML file** (no external CDN, all CSS inlined) mimicking Discord's UI, uploaded directly as a Discord file attachment.

### Permission Diffs
`utils/permissions_diff.py` produces clean `✅ Allow / ❌ Deny / ⬜ Reset` diffs for channel overwrites, and `🟢 Added / 🔴 Removed` diffs for role permissions — with ⚠️ warnings for sensitive permissions like `ADMINISTRATOR`, `BAN_MEMBERS`, `MANAGE_WEBHOOKS`.

---

## 🔐 Required Bot Permissions

| Permission | Reason |
|---|---|
| View Audit Log | Executor attribution on all mod actions |
| Manage Webhooks | Reading webhook changes |
| Read Message History | Message cache and edit diff |
| View Channel | Access to log all channels |
| Send Messages | Posting log embeds |
| Attach Files | Uploading HTML transcripts |
| Embed Links | Sending rich embeds |
| Manage Guild | Reading invites for invite tracker |

---

## 📝 Notes

- The bot uses `discord.Intents.all()` — ensure all privileged intents are enabled in the Developer Portal.
- Set `DEV_GUILD_ID` in `.env` during development to sync slash commands instantly (instead of waiting up to 1 hour for global sync).
- All timestamps are in **UTC**.
- Voice session durations are stored in the `voice_sessions` PostgreSQL table for historical analysis.
