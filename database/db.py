"""
database/db.py — asyncpg Connection Pool & CRUD Helpers
========================================================
Provides a singleton connection pool and all database operations used
across the bot's cogs.  Import `Database` from this module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

log = logging.getLogger(__name__)

# Module-level in-memory cache for guild languages {guild_id: "en" | "ar"}
_guild_lang_cache: dict[int, str] = {}


class Database:
    """
    Thin wrapper around an asyncpg connection pool.

    Usage
    -----
    db = Database()
    await db.init(dsn)
    ...
    await db.close()
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self, dsn: str, *, schema_path: str = "database/schema.sql") -> None:
        """Create the connection pool and apply the schema."""
        self._pool = await asyncpg.create_pool(
            dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        log.info("Database pool established.")
        await self._apply_schema(schema_path)

    async def _apply_schema(self, schema_path: str) -> None:
        """Run schema.sql to ensure all tables exist."""
        try:
            with open(schema_path, "r", encoding="utf-8") as fh:
                sql = fh.read()
            async with self._pool.acquire() as conn:
                await conn.execute(sql)
                await conn.execute(
                    "ALTER TABLE member_history ADD COLUMN IF NOT EXISTS message_count INT NOT NULL DEFAULT 0;"
                )
                await conn.execute(
                    "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';"
                )
                # command_channel_rules — channel routing per command/cog
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS command_channel_rules (
                        guild_id    BIGINT NOT NULL,
                        name        TEXT   NOT NULL,
                        channel_id  BIGINT NOT NULL,
                        rule_type   TEXT   NOT NULL DEFAULT 'command',
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (guild_id, name, channel_id)
                    );
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ccr_guild ON command_channel_rules (guild_id);"
                )
            log.info("Schema applied successfully.")
        except FileNotFoundError:
            log.warning("schema.sql not found at %s — skipping auto-migration.", schema_path)
        except Exception as exc:
            log.error("Schema application failed: %s", exc)
            raise

    async def close(self) -> None:
        """Gracefully close the connection pool."""
        if self._pool:
            await self._pool.close()
            log.info("Database pool closed.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("Database pool is not initialised. Call `await db.init(dsn)` first.")
        return self._pool

    async def execute(self, query: str, *args: Any) -> str:
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def fetchall(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Alias for fetch() — returns a list of asyncpg.Record objects."""
        return await self.fetch(query, *args)


    # ------------------------------------------------------------------
    # Guild Settings
    # ------------------------------------------------------------------

    async def ensure_guild(self, guild_id: int) -> None:
        """Insert a default guild_settings row if one does not exist."""
        await self.execute(
            """
            INSERT INTO guild_settings (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING
            """,
            guild_id,
        )

    async def get_guild_settings(self, guild_id: int) -> asyncpg.Record | None:
        return await self.fetchrow(
            "SELECT * FROM guild_settings WHERE guild_id = $1", guild_id
        )

    async def get_prefix(self, guild_id: int) -> str:
        val = await self.fetchval(
            "SELECT prefix FROM guild_settings WHERE guild_id = $1", guild_id
        )
        return val or "!"

    async def get_guild_language(self, guild_id: int) -> str:
        """Get the language code ('en' or 'ar') configured for a guild."""
        if guild_id in _guild_lang_cache:
            return _guild_lang_cache[guild_id]
        val = await self.fetchval(
            "SELECT language FROM guild_settings WHERE guild_id = $1", guild_id
        )
        lang = val or "en"
        _guild_lang_cache[guild_id] = lang
        return lang

    async def set_guild_language(self, guild_id: int, lang_code: str) -> None:
        """Set the language code ('en' or 'ar') for a guild."""
        await self.ensure_guild(guild_id)
        await self.execute(
            "UPDATE guild_settings SET language = $2 WHERE guild_id = $1",
            guild_id,
            lang_code,
        )
        _guild_lang_cache[guild_id] = lang_code

    async def is_ignored(self, guild_id: int, entity_type: str, entity_id: int) -> bool:
        """
        Check whether a given entity (channel / role / user) is on the ignore list.

        Parameters
        ----------
        entity_type:
            One of ``"channel"``, ``"role"``, ``"user"``.
        """
        column_map = {
            "channel": "ignored_channels",
            "role":    "ignored_roles",
            "user":    "ignored_users",
        }
        col = column_map.get(entity_type)
        if col is None:
            return False
        result = await self.fetchval(
            f"SELECT $2 = ANY(SELECT unnest({col}) FROM guild_settings WHERE guild_id = $1)",
            guild_id,
            entity_id,
        )
        return bool(result)

    async def ignore_add(self, guild_id: int, entity_type: str, entity_id: int) -> None:
        """Add an entity to the ignore list for a guild."""
        await self.ensure_guild(guild_id)
        column_map = {
            "channel": "ignored_channels",
            "role":    "ignored_roles",
            "user":    "ignored_users",
        }
        col = column_map[entity_type]
        await self.execute(
            f"""
            UPDATE guild_settings
            SET {col} = array_append({col}, $2)
            WHERE guild_id = $1
              AND NOT ($2 = ANY({col}))
            """,
            guild_id,
            entity_id,
        )

    async def ignore_remove(self, guild_id: int, entity_type: str, entity_id: int) -> None:
        """Remove an entity from the ignore list for a guild."""
        column_map = {
            "channel": "ignored_channels",
            "role":    "ignored_roles",
            "user":    "ignored_users",
        }
        col = column_map[entity_type]
        await self.execute(
            f"""
            UPDATE guild_settings
            SET {col} = array_remove({col}, $2)
            WHERE guild_id = $1
            """,
            guild_id,
            entity_id,
        )

    # ------------------------------------------------------------------
    # Log Channels
    # ------------------------------------------------------------------

    async def get_log_channel(self, guild_id: int, category: str) -> int | None:
        """Return the channel_id for a log category, or None if unset."""
        return await self.fetchval(
            """
            SELECT channel_id FROM log_channels
            WHERE guild_id = $1 AND category = $2
            """,
            guild_id,
            category,
        )

    async def set_log_channel(self, guild_id: int, category: str, channel_id: int) -> None:
        """Upsert a log channel mapping."""
        await self.execute(
            """
            INSERT INTO log_channels (guild_id, category, channel_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, category)
            DO UPDATE SET channel_id = EXCLUDED.channel_id, set_at = NOW()
            """,
            guild_id,
            category,
            channel_id,
        )

    async def get_all_log_channels(self, guild_id: int) -> list[asyncpg.Record]:
        """Return all configured log channel mappings for a guild."""
        return await self.fetch(
            "SELECT category, channel_id FROM log_channels WHERE guild_id = $1 ORDER BY category",
            guild_id,
        )

    async def remove_log_channel(self, guild_id: int, category: str) -> bool:
        """Remove a log channel mapping for a category/event."""
        res = await self.execute(
            "DELETE FROM log_channels WHERE guild_id = $1 AND category = $2",
            guild_id, category,
        )
        return res != "DELETE 0"

    async def clear_all_log_channels(self, guild_id: int) -> int:
        """Clear all log channel mappings for a guild."""
        res = await self.execute(
            "DELETE FROM log_channels WHERE guild_id = $1", guild_id
        )
        return int(res.split()[-1]) if res.startswith("DELETE") else 0

    # ------------------------------------------------------------------
    # Member History
    # ------------------------------------------------------------------

    async def ensure_member(self, user_id: int, guild_id: int) -> None:
        await self.execute(
            """
            INSERT INTO member_history (user_id, guild_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, guild_id) DO NOTHING
            """,
            user_id,
            guild_id,
        )

    async def append_nick_history(
        self, user_id: int, guild_id: int, nick: str | None, timestamp: datetime
    ) -> None:
        """Append a nickname change record to the member's history."""
        await self.ensure_member(user_id, guild_id)
        entry = json.dumps({"value": nick, "timestamp": timestamp.isoformat()})
        await self.execute(
            """
            UPDATE member_history
            SET nick_history = nick_history || $3::jsonb
            WHERE user_id = $1 AND guild_id = $2
            """,
            user_id,
            guild_id,
            entry,
        )

    async def append_username_history(
        self, user_id: int, username: str, timestamp: datetime
    ) -> None:
        """
        Append a username change record.  Username changes are guild-agnostic,
        so we update *all* member_history rows for this user.
        """
        entry = json.dumps({"value": username, "timestamp": timestamp.isoformat()})
        await self.execute(
            """
            UPDATE member_history
            SET username_history = username_history || $2::jsonb
            WHERE user_id = $1
            """,
            user_id,
            entry,
        )

    async def set_member_joined_at(
        self, user_id: int, guild_id: int, joined_at: datetime
    ) -> None:
        await self.ensure_member(user_id, guild_id)
        await self.execute(
            """
            UPDATE member_history
            SET joined_at = $3
            WHERE user_id = $1 AND guild_id = $2
            """,
            user_id,
            guild_id,
            joined_at,
        )

    async def get_member_joined_at(self, user_id: int, guild_id: int) -> datetime | None:
        return await self.fetchval(
            "SELECT joined_at FROM member_history WHERE user_id = $1 AND guild_id = $2",
            user_id,
            guild_id,
        )

    async def increment_message_count(self, user_id: int, guild_id: int) -> None:
        """Increment message count for a member."""
        await self.ensure_member(user_id, guild_id)
        await self.execute(
            """
            UPDATE member_history
            SET message_count = message_count + 1
            WHERE user_id = $1 AND guild_id = $2
            """,
            user_id,
            guild_id,
        )

    async def get_message_count(self, user_id: int, guild_id: int) -> int:
        """Get total recorded messages sent by member in a guild."""
        val = await self.fetchval(
            "SELECT message_count FROM member_history WHERE user_id = $1 AND guild_id = $2",
            user_id,
            guild_id,
        )
        return val or 0

    # ------------------------------------------------------------------
    # Cached Invites
    # ------------------------------------------------------------------

    async def get_cached_invites(self, guild_id: int) -> list[asyncpg.Record]:
        """Return all cached invites for a guild."""
        return await self.fetch(
            "SELECT * FROM cached_invites WHERE guild_id = $1", guild_id
        )

    async def upsert_invite(
        self,
        guild_id: int,
        code: str,
        inviter_id: int | None,
        uses: int,
        max_uses: int | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        await self.execute(
            """
            INSERT INTO cached_invites
                (guild_id, invite_code, inviter_id, uses, max_uses, created_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (guild_id, invite_code)
            DO UPDATE SET
                uses       = EXCLUDED.uses,
                inviter_id = COALESCE(EXCLUDED.inviter_id, cached_invites.inviter_id),
                updated_at = NOW()
            """,
            guild_id,
            code,
            inviter_id,
            uses,
            max_uses,
            created_at,
            expires_at,
        )

    async def delete_invite(self, guild_id: int, code: str) -> None:
        await self.execute(
            "DELETE FROM cached_invites WHERE guild_id = $1 AND invite_code = $2",
            guild_id,
            code,
        )

    async def bulk_sync_invites(self, guild_id: int, invites: list) -> None:
        """
        Sync the full invite list for a guild atomically.
        Accepts a list of ``discord.Invite`` objects.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM cached_invites WHERE guild_id = $1", guild_id
                )
                for inv in invites:
                    await conn.execute(
                        """
                        INSERT INTO cached_invites
                            (guild_id, invite_code, inviter_id, uses, max_uses, created_at, expires_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        guild_id,
                        inv.code,
                        inv.inviter.id if inv.inviter else None,
                        inv.uses or 0,
                        inv.max_uses,
                        inv.created_at,
                        inv.expires_at,
                    )

    # ------------------------------------------------------------------
    # Voice Sessions
    # ------------------------------------------------------------------

    async def open_voice_session(
        self, user_id: int, guild_id: int, channel_id: int
    ) -> int:
        """Insert a new voice session and return its row ID."""
        return await self.fetchval(
            """
            INSERT INTO voice_sessions (user_id, guild_id, channel_id)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            user_id,
            guild_id,
            channel_id,
        )

    async def close_voice_session(self, session_id: int, left_at: datetime) -> int | None:
        """Mark a voice session as ended and compute duration in seconds."""
        return await self.fetchval(
            """
            UPDATE voice_sessions
            SET left_at    = $2,
                duration_s = EXTRACT(EPOCH FROM ($2 - joined_at))::INT
            WHERE id = $1
            RETURNING duration_s
            """,
            session_id,
            left_at,
        )

    async def get_total_voice_time(self, user_id: int, guild_id: int) -> int:
        """Return total duration in seconds spent in voice channels for a guild."""
        val = await self.fetchval(
            """
            SELECT COALESCE(SUM(duration_s), 0)::INT
            FROM voice_sessions
            WHERE user_id = $1 AND guild_id = $2 AND duration_s IS NOT NULL
            """,
            user_id,
            guild_id,
        )
        return val or 0


# ---------------------------------------------------------------------------
# Module-level singleton — import and use `db` everywhere.
# ---------------------------------------------------------------------------
db = Database()
