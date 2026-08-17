"""
database/setup_db.py — Automatic Database Initializer & Verification
====================================================================
Used by Install.bat or run standalone to:
  1. Parse DB_DSN from .env
  2. Ensure PostgreSQL service is running and accessible
  3. Create the database if it doesn't exist
  4. Apply database/schema.sql
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlparse

import asyncpg
from dotenv import load_dotenv

# Load .env
load_dotenv()


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

    # Step 1: Connect to default 'postgres' database to check/create target database
    print(f"Connecting to PostgreSQL server at {host}:{port} as user '{user}'…")
    try:
        root_conn = await asyncpg.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database="postgres",
        )
    except Exception as exc:
        print(f"❌ Failed to connect to PostgreSQL server: {exc}")
        print("\nPossible solutions:")
        print("  1. Make sure PostgreSQL service is running.")
        print("  2. Check username and password in .env (DB_DSN).")
        return False

    try:
        # Check if target database exists
        exists = await root_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if not exists:
            print(f"Creating database '{db_name}'…")
            await root_conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"✓ Database '{db_name}' created successfully.")
        else:
            print(f"✓ Database '{db_name}' already exists.")
    finally:
        await root_conn.close()

    # Step 2: Connect to target database and apply schema.sql
    print(f"Applying schema to '{db_name}'…")
    try:
        db_conn = await asyncpg.connect(dsn)
    except Exception as exc:
        print(f"❌ Failed to connect to target database '{db_name}': {exc}")
        return False

    try:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
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
