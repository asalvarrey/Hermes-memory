-- ============================================================
-- Hermes Memory Plugin - Supabase Migration
-- Version: 1.0.0
-- Description: Creates the tables needed for Hermes Agent's
--              persistent memory layer via Supabase.
-- ============================================================

-- Enable pgvector if not already enabled
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

-- -----------------------------------------------------------
-- Table: hermes_memory
-- Stores all memory entries with vector embeddings for
-- semantic search across sessions.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hermes_memory (
    id          UUID PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
    user_id     TEXT NOT NULL DEFAULT 'default',
    session_id  TEXT,
    content     TEXT NOT NULL,
    embedding   extensions.vector(1536),
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Table: hermes_users
-- Stores user profiles and preferences persistently.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hermes_users (
    id          UUID PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
    user_id     TEXT NOT NULL UNIQUE,
    profile     JSONB DEFAULT '{}'::jsonb,
    embedding   extensions.vector(1536),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Table: hermes_sessions
-- Tracks conversation sessions for context management.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hermes_sessions (
    id          UUID PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
    session_id  TEXT NOT NULL UNIQUE,
    user_id     TEXT NOT NULL DEFAULT 'default',
    summary     TEXT,
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Table: hermes_skills
-- Mirrors skills across Hermes instances for portability.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hermes_skills (
    id          UUID PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}'::jsonb,
    version     TEXT DEFAULT '1.0.0',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Indexes for performance
-- -----------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_memory_user_id ON public.hermes_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_session_id ON public.hermes_memory(session_id);
CREATE INDEX IF NOT EXISTS idx_memory_created_at ON public.hermes_memory(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_embedding ON public.hermes_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_users_user_id ON public.hermes_users(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON public.hermes_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_skills_name ON public.hermes_skills(name);

-- -----------------------------------------------------------
-- Helper function: update updated_at automatically
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------
-- Triggers for updated_at
-- -----------------------------------------------------------
DROP TRIGGER IF EXISTS trg_users_updated_at ON public.hermes_users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON public.hermes_users
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS trg_sessions_updated_at ON public.hermes_sessions;
CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON public.hermes_sessions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS trg_skills_updated_at ON public.hermes_skills;
CREATE TRIGGER trg_skills_updated_at
    BEFORE UPDATE ON public.hermes_skills
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- -----------------------------------------------------------
-- Row Level Security (opened for service_role)
-- -----------------------------------------------------------
ALTER TABLE public.hermes_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hermes_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hermes_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hermes_skills ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS automatically, but we add policies
-- for the anon key if needed later
CREATE POLICY "service_role_all_memory" ON public.hermes_memory
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_users" ON public.hermes_users
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_sessions" ON public.hermes_sessions
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_skills" ON public.hermes_skills
    FOR ALL TO service_role USING (true) WITH CHECK (true);
