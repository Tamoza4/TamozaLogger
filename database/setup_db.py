"""
database/setup_db.py — Automatic Database Initializer & Verification
====================================================================
Used by install.sh / Install.bat or run standalone to:
  1. Parse DB_DSN from .env
  2. Verify connection to the PostgreSQL database
  3. Create the database if it doesn't exist yet
  4. Apply database/schema.sql to build tables and indexes
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlparse

import asyncpg
from dotenv import load_dotenv

# Force reload .env
load_dotenv(override=True)


async def setup_database() -> bool:
    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("❌ ERROR: DB_DSN not found in .env file.")
        print("   Please make sure .env exists and contains a valid DB_DSN.")
        return False

    parsed = urlparse(dsn)
    db_name = parsed.path.lstrip("/") or "tamoza_logger"
    user = parsed.username or "postgres"
    password = parsed.password or ""
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    # Attempt 1: Try connecting directly to the target database
    print(f"Connecting to database '{db_name}' at {host}:{port} as user '{user}'…")
    try:
        db_conn = await asyncpg.connect(dsn)
        print(f"✓ Connected to database '{db_name}'.")
    except asyncpg.InvalidCatalogNameError:
        # Database does not exist yet; attempt to create it via 'postgres' DB
        print(f"Database '{db_name}' does not exist. Creating it…")
        try:
            root_conn = await asyncpg.connect(
                user=user,
                password=password,
                host=host,
                port=port,
                database="postgres",
            )
            await root_conn.execute(f'CREATE DATABASE "{db_name}"')
            await root_conn.close()
            print(f"✓ Database '{db_name}' created successfully.")
            # Now reconnect to newly created DB
            db_conn = await asyncpg.connect(dsn)
        except Exception as exc:
            print(f"❌ Failed to create database '{db_name}': {exc}")
            return False
    except Exception as exc:
        print(f"❌ Failed to connect to PostgreSQL server: {exc}")
        print("\nPossible solutions:")
        print("  1. Make sure PostgreSQL service is running.")
        print("  2. Check username and password in .env (DB_DSN).")
        return False

    # Apply schema.sql
    print(f"Applying schema to '{db_name}'…")
    try:
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as fh:
                sql = fh.read()
            await db_conn.execute(sql)
            print("✓ Database schema applied successfully.")
        else:
            print(f"⚠️ Warning: schema.sql not found at {schema_path}")
    except Exception as exc:
        print(f"❌ Schema execution error: {exc}")
        return False
    finally:
        await db_conn.close()

    print("\n✅ Database setup complete!")
    return True


if __name__ == "__main__":
    success = asyncio.run(setup_database())
    sys.exit(0 if success else 1)
