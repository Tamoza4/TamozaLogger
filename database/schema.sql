-- =============================================================================
-- TamozaLogger — PostgreSQL Schema
-- Apply with: psql -U <user> -d <dbname> -f schema.sql
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Guild Settings
-- Stores per-guild configuration including prefix and ignored entities.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id          BIGINT PRIMARY KEY,
    prefix            TEXT    NOT NULL DEFAULT '!',
    language          TEXT    NOT NULL DEFAULT 'en',
    ignored_channels  BIGINT[] NOT NULL DEFAULT '{}',
    ignored_roles     BIGINT[] NOT NULL DEFAULT '{}',
    ignored_users     BIGINT[] NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Log Channels
-- Maps a (guild_id, category) pair to a target log channel.
-- Categories: messages | members | voice | channels | roles | server | mod
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS log_channels (
    guild_id    BIGINT  NOT NULL,
    category    TEXT    NOT NULL,
    channel_id  BIGINT  NOT NULL,
    set_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, category)
);

CREATE INDEX IF NOT EXISTS idx_log_channels_guild
    ON log_channels (guild_id);

-- ---------------------------------------------------------------------------
-- Member History
-- Stores per-member nickname and username history as JSONB arrays.
-- Each entry: {"value": "...", "timestamp": "ISO8601"}
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS member_history (
    user_id          BIGINT NOT NULL,
    guild_id         BIGINT NOT NULL,
    nick_history     JSONB  NOT NULL DEFAULT '[]',
    username_history JSONB  NOT NULL DEFAULT '[]',
    message_count    INT    NOT NULL DEFAULT 0,
    joined_at        TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, guild_id)
);

CREATE INDEX IF NOT EXISTS idx_member_history_guild
    ON member_history (guild_id);

-- ---------------------------------------------------------------------------
-- Cached Invites
-- Stores a snapshot of all invites per guild for the native invite tracker.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cached_invites (
    guild_id    BIGINT NOT NULL,
    invite_code TEXT   NOT NULL,
    inviter_id  BIGINT,
    uses        INT    NOT NULL DEFAULT 0,
    max_uses    INT,
    created_at  TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, invite_code)
);

CREATE INDEX IF NOT EXISTS idx_cached_invites_guild
    ON cached_invites (guild_id);

-- ---------------------------------------------------------------------------
-- Voice Sessions (optional — tracks time-in-channel)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS voice_sessions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT      NOT NULL,
    guild_id    BIGINT      NOT NULL,
    channel_id  BIGINT      NOT NULL,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    left_at     TIMESTAMPTZ,
    duration_s  INT
);

CREATE INDEX IF NOT EXISTS idx_voice_sessions_user_guild
    ON voice_sessions (user_id, guild_id);

-- ---------------------------------------------------------------------------
-- Helper: auto-update updated_at column
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'set_guild_settings_updated_at'
    ) THEN
        CREATE TRIGGER set_guild_settings_updated_at
        BEFORE UPDATE ON guild_settings
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'set_member_history_updated_at'
    ) THEN
        CREATE TRIGGER set_member_history_updated_at
        BEFORE UPDATE ON member_history
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    END IF;
END
$$;
