"""
bot.py — TamozaLogger Entry Point
===================================
Subclassed discord.ext.commands.Bot with:
  - asyncpg database pool lifecycle
  - Automatic Cog loading
  - Global application command sync
  - Dynamic command prefix from database
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

import aiohttp
import discord
from discord.ext import commands

import config
from database.db import db

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tamoza_logger.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("tamoza")

# Silence noisy discord.py sub-loggers
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Cog discovery
# ---------------------------------------------------------------------------

COGS: list[str] = [
    "cogs.settings",
    "cogs.message_logs",
    "cogs.member_logs",
    "cogs.voice_logs",
    "cogs.channel_logs",
    "cogs.role_logs",
    "cogs.server_logs",
    "cogs.whois",
    "cogs.help",
]


# ---------------------------------------------------------------------------
# Bot subclass
# ---------------------------------------------------------------------------

class TamozaLogger(commands.Bot):
    """
    Enterprise Discord Logging & Forensics Bot.

    Attributes
    ----------
    db:
        The shared ``Database`` instance (asyncpg pool wrapper).
    """

    def __init__(self) -> None:
        intents = discord.Intents.all()  # Requires privileged intents in the Dev Portal

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,  # Custom help handled via slash commands
            case_insensitive=True,
            application_id=config.APPLICATION_ID or None,
        )

        self.db = db

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def setup_hook(self) -> None:
        """Called once before the bot connects.  Initialise DB and load Cogs."""
        log.info("Initialising database pool…")
        await self.db.init(config.DB_DSN)

        log.info("Loading cogs…")
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("  ✓ Loaded %s", cog)
            except Exception as exc:
                log.error("  ✗ Failed to load %s: %s", cog, exc, exc_info=True)

        # Sync application commands
        if config.DEV_GUILD_ID:
            guild_obj = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            try:
                await self.tree.sync(guild=guild_obj)
                log.info("Slash commands synced to dev guild %d", config.DEV_GUILD_ID)
            except discord.Forbidden:
                log.warning(
                    "Could not sync to dev guild %d (bot not in that guild yet). "
                    "Falling back to global sync.",
                    config.DEV_GUILD_ID,
                )
                await self.tree.sync()
                log.info("Slash commands synced globally (may take up to 1 hour).")
            except discord.HTTPException as exc:
                log.error("Slash command sync failed: %s — trying global sync.", exc)
                await self.tree.sync()
        else:
            await self.tree.sync()
            log.info("Slash commands synced globally (may take up to 1 hour).")

    async def close(self) -> None:
        """Gracefully shut down: close DB pool before disconnecting."""
        log.info("Shutting down — closing database pool…")
        await self.db.close()
        await super().close()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def on_ready(self) -> None:
        log.info("=" * 60)
        log.info("TamozaLogger is online!")
        log.info("  User   : %s (ID: %d)", self.user, self.user.id)
        log.info("  Guilds : %d", len(self.guilds))
        log.info("=" * 60)

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers | /log set",
            )
        )

        # ── Seed invite cache for every guild the bot is already in ──
        seeded = 0
        for guild in self.guilds:
            await self.db.ensure_guild(guild.id)
            try:
                invites = await guild.invites()
                await self.db.bulk_sync_invites(guild.id, invites)
                seeded += 1
            except discord.Forbidden:
                log.debug("No MANAGE_GUILD in %s — skipping invite seed.", guild.name)
            except discord.HTTPException as exc:
                log.warning("Failed to seed invites for %s: %s", guild.name, exc)
        log.info("Invite cache seeded for %d/%d guilds.", seeded, len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Ensure guild settings row and prime invite cache on join."""
        await self.db.ensure_guild(guild.id)
        log.info("Joined guild: %s (%d)", guild.name, guild.id)

        # Prime invite cache
        try:
            invites = await guild.invites()
            await self.db.bulk_sync_invites(guild.id, invites)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        log.error("Command error in %s: %s", ctx.command, error, exc_info=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    max_retries = 10
    retry_delay = 5

    for attempt in range(1, max_retries + 1):
        bot = TamozaLogger()
        try:
            async with bot:
                await bot.start(config.BOT_TOKEN)
            break
        except (aiohttp.ClientConnectorError, aiohttp.ClientConnectorDNSError, OSError) as exc:
            log.warning(
                "Network/DNS connection delay (%s). Retrying in %ds (attempt %d/%d)...",
                exc, retry_delay, attempt, max_retries,
            )
            if attempt == max_retries:
                log.error("Maximum network connection retries reached. Exiting.")
                raise
            await asyncio.sleep(retry_delay)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Received KeyboardInterrupt — shutting down.")
