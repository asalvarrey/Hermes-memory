-- ============================================================
-- Hermes Memory Plugin - Supabase Migration
-- Version: 1.0.1
-- Description: Adds the vector match RPC used by the plugin
--              to retrieve semantically similar memories.
-- ============================================================

CREATE OR REPLACE FUNCTION public.match_hermes_memory(
    query_embedding extensions.vector(1536),
    match_threshold double precision DEFAULT 0.75,
    match_count integer DEFAULT 10,
    filter_user_id text DEFAULT NULL,
    filter_session_id text DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    user_id text,
    session_id text,
    content text,
    metadata jsonb,
    similarity double precision,
    created_at timestamptz
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        m.id,
        m.user_id,
        m.session_id,
        m.content,
        m.metadata,
        1 - (m.embedding <=> query_embedding) AS similarity,
        m.created_at
    FROM public.hermes_memory AS m
    WHERE m.embedding IS NOT NULL
      AND (filter_user_id IS NULL OR m.user_id = filter_user_id)
      AND (filter_session_id IS NULL OR m.session_id = filter_session_id)
      AND 1 - (m.embedding <=> query_embedding) >= match_threshold
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_count;
$$;

COMMENT ON FUNCTION public.match_hermes_memory(
    extensions.vector(1536),
    double precision,
    integer,
    text,
    text
) IS 'Returns the most similar memory rows using cosine similarity over embeddings.';
