-- ==============================================================================
-- Production RAG Blueprint - PostgreSQL 16 + pgvector Baseline Schema
-- Consolidated & Unified Schema with 5-Way Hybrid Search & Semantic Caching
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- 2. SCHEMA MIGRATIONS LEDGER
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum VARCHAR(64)
);

-- 3. CORE ENTITIES (FRBR Extended Model)

CREATE TABLE IF NOT EXISTS collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    slug TEXT,
    description TEXT,
    icon TEXT DEFAULT 'book-open',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS works (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_title TEXT NOT NULL,
    original_title TEXT,
    canonical_author TEXT DEFAULT 'Author',
    original_language TEXT DEFAULT 'ar',
    domain TEXT DEFAULT 'General',
    provisional BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS editions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    work_id UUID NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    edition_title TEXT,
    editor TEXT,
    translator TEXT,
    publisher TEXT,
    publication_year INTEGER,
    publication_place TEXT,
    edition_language TEXT NOT NULL DEFAULT 'ar',
    is_translation BOOLEAN DEFAULT false,
    isbn TEXT,
    provisional BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    edition_id UUID REFERENCES editions(id) ON DELETE SET NULL,
    collection_id UUID REFERENCES collections(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    author TEXT DEFAULT 'Author',
    file_name TEXT,
    file_type TEXT DEFAULT 'article',
    file_size BIGINT DEFAULT 0,
    file_hash VARCHAR(64),
    total_pages INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    checkpoint_stage VARCHAR(32) DEFAULT 'INIT',
    checkpoint_data JSONB DEFAULT '{}'::jsonb,
    embedding_model TEXT DEFAULT 'gemini-embedding-2',
    embedding_version TEXT DEFAULT 'v2',
    category TEXT DEFAULT 'General',
    description TEXT,
    tags TEXT[] DEFAULT '{}'::text[],
    language TEXT DEFAULT 'ar',
    cover_url TEXT,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    parent_chunk_id UUID REFERENCES document_chunks(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_type TEXT DEFAULT 'CHILD' CHECK (chunk_type IN ('PARENT', 'CHILD', 'STANDALONE')),
    depth INTEGER DEFAULT 1,
    content TEXT NOT NULL,
    clean_content TEXT,
    chapter_title TEXT,
    page_number INTEGER,
    token_count INTEGER DEFAULT 0,
    language VARCHAR(16) DEFAULT 'ar',
    embedding vector(768),
    embedding_model TEXT DEFAULT 'gemini-embedding-2',
    embedding_version TEXT DEFAULT 'v2',
    content_hash VARCHAR(64),
    section_path TEXT[] DEFAULT '{}'::text[],
    context_header TEXT,
    volume_number INTEGER,
    volume_title TEXT,
    breadcrumb TEXT,
    has_footnotes BOOLEAN DEFAULT false,
    footnotes_data JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('arabic'::regconfig, content)) STORED,
    tsv_simple tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content)) STORED,
    tsv_english tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, content)) STORED,
    tsv_spanish tsvector GENERATED ALWAYS AS (to_tsvector('spanish'::regconfig, COALESCE(content, ''))) STORED,
    tsv_portuguese tsvector GENERATED ALWAYS AS (to_tsvector('portuguese'::regconfig, COALESCE(content, ''))) STORED
);

-- 4. CONVERSATIONAL RAG, PERSONAS & USERS

CREATE TABLE IF NOT EXISTS chat_conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id UUID REFERENCES collections(id) ON DELETE SET NULL,
    title TEXT DEFAULT 'محادثة جديدة',
    user_identifier TEXT DEFAULT 'local-user',
    persona_mode TEXT DEFAULT 'standard',
    system_prompt_override TEXT,
    selected_document_ids UUID[],
    temperature FLOAT DEFAULT 0.2,
    is_shared BOOLEAN DEFAULT false,
    share_id VARCHAR(64) UNIQUE,
    shared_at TIMESTAMPTZ,
    session_state JSONB DEFAULT '{"goal": null, "decisions": [], "turn_count": 0, "constraints": [], "preferences": {}, "active_topic": null, "last_condensed_turn": 0, "unresolved_questions": []}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sources JSONB DEFAULT '[]'::jsonb,
    citations JSONB DEFAULT '[]'::jsonb,
    suggestions JSONB DEFAULT '[]'::jsonb,
    token_usage JSONB DEFAULT '{}'::jsonb,
    grounding_audit JSONB DEFAULT '{}'::jsonb,
    persona_mode TEXT,
    feedback SMALLINT DEFAULT 0,
    feedback_tag TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_conversation_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. SEMANTIC QUERY CACHE (MULTI-DIMENSIONAL SCOPING)

CREATE TABLE IF NOT EXISTS semantic_query_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text TEXT NOT NULL,
    normalized_query TEXT NOT NULL DEFAULT '',
    query_embedding vector(768) NOT NULL,
    response_text TEXT NOT NULL,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    persona VARCHAR(50) NOT NULL DEFAULT 'standard',
    language VARCHAR(10) NOT NULL DEFAULT 'ar',
    answer_shape VARCHAR(50) NOT NULL DEFAULT 'standard',
    filter_hash VARCHAR(64) NOT NULL DEFAULT 'ALL',
    embedding_model VARCHAR(64) NOT NULL DEFAULT 'gemini-embedding-2',
    corpus_version VARCHAR(32) NOT NULL DEFAULT 'v1',
    schema_version VARCHAR(32) NOT NULL DEFAULT 'v1',
    format_directive VARCHAR(32) NOT NULL DEFAULT 'none',
    hit_count INTEGER NOT NULL DEFAULT 1,
    grounding_audit JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_hit_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + interval '7 days')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_semantic_cache_entry 
ON semantic_query_cache (
    normalized_query, persona, language, filter_hash, 
    format_directive, embedding_model, corpus_version, schema_version
);

-- 6. SECURITY & INGESTION JOBS

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_prefix VARCHAR(12) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'reader' CHECK (role IN ('admin', 'ingestor', 'reader')),
    rate_limit_rpm INTEGER DEFAULT 120,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type TEXT NOT NULL,
    target_id UUID,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'completed', 'failed')),
    progress INTEGER DEFAULT 0,
    error_message TEXT,
    details JSONB DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    actor_id VARCHAR(100) NOT NULL,
    actor_role VARCHAR(20) NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_resource VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent TEXT,
    details JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO system_settings (key, value, description)
VALUES ('corpus_version', '{"version": "v1"}'::jsonb, 'Global knowledge corpus version')
ON CONFLICT (key) DO NOTHING;

-- 7. PERFORMANCE INDEXES

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
ON document_chunks 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_tsv ON document_chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_tsv_simple ON document_chunks USING gin (tsv_simple);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_tsv_english ON document_chunks USING gin (tsv_english);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_tsv_spanish ON document_chunks USING gin (tsv_spanish);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_tsv_portuguese ON document_chunks USING gin (tsv_portuguese);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_parent_id ON document_chunks (parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_filter ON document_chunks (document_id, chunk_type) WHERE chunk_type != 'PARENT';

CREATE INDEX IF NOT EXISTS idx_semantic_cache_vector_hnsw 
ON semantic_query_cache 
USING hnsw (query_embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_semantic_cache_scope 
ON semantic_query_cache (persona, language, format_directive, filter_hash, expires_at);

-- 8. STORED PROCEDURES (5-WAY HYBRID RRF RETRIEVAL & SEMANTIC CACHE LOOKUP)

CREATE OR REPLACE FUNCTION search_chunks_hybrid(
    query_embedding vector,
    query_text text,
    match_count integer DEFAULT 8,
    filter_doc_ids uuid[] DEFAULT NULL,
    filter_collection_id uuid DEFAULT NULL,
    vector_weight double precision DEFAULT 0.7,
    keyword_weight double precision DEFAULT 0.3,
    filter_languages text[] DEFAULT NULL,
    preferred_languages text[] DEFAULT NULL,
    language_boost double precision DEFAULT 0.05
) RETURNS TABLE(
    id uuid,
    document_id uuid,
    document_title text,
    document_author text,
    work_id uuid,
    work_title text,
    edition_id uuid,
    edition_title text,
    edition_language text,
    chunk_language text,
    content text,
    chapter_title text,
    page_number integer,
    chunk_index integer,
    chunk_type text,
    parent_chunk_id uuid,
    depth integer,
    volume_number integer,
    breadcrumb text,
    has_footnotes boolean,
    footnotes_data jsonb,
    vector_similarity double precision,
    text_score double precision,
    combined_score double precision
)
LANGUAGE plpgsql
AS $$
DECLARE
    candidate_pool_size INT := GREATEST(match_count * 5, 30);
    rrf_k CONSTANT FLOAT := 60.0;
BEGIN
    RETURN QUERY
    WITH scoped_chunks AS (
        SELECT 
            dc.id,
            dc.document_id,
            d.title::TEXT AS doc_title,
            COALESCE(d.author, 'Author')::TEXT AS doc_author,
            w.id AS w_id,
            w.canonical_title::TEXT AS w_title,
            e.id AS e_id,
            e.edition_title::TEXT AS e_title,
            COALESCE(e.edition_language, d.language, 'ar')::TEXT AS e_lang,
            COALESCE(dc.language, d.language, e.edition_language, 'ar')::TEXT AS c_lang,
            dc.content,
            dc.chapter_title,
            dc.page_number,
            dc.chunk_index,
            dc.chunk_type,
            dc.parent_chunk_id,
            dc.depth,
            dc.volume_number,
            dc.breadcrumb,
            dc.has_footnotes,
            dc.footnotes_data,
            dc.embedding,
            dc.tsv,
            dc.tsv_simple,
            dc.tsv_english,
            dc.tsv_spanish,
            dc.tsv_portuguese
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        LEFT JOIN editions e ON e.id = d.edition_id
        LEFT JOIN works w ON w.id = e.work_id
        WHERE (filter_doc_ids IS NULL OR dc.document_id = ANY(filter_doc_ids))
          AND (filter_collection_id IS NULL OR d.collection_id = filter_collection_id)
          AND (dc.chunk_type != 'PARENT' OR dc.chunk_type IS NULL)
          AND (
            filter_languages IS NULL 
            OR COALESCE(dc.language, d.language, e.edition_language, 'ar') = ANY(filter_languages)
          )
    ),
    vector_candidates AS (
        SELECT 
            sc.id,
            (1 - (sc.embedding <=> query_embedding))::FLOAT AS v_sim,
            ROW_NUMBER() OVER (ORDER BY sc.embedding <=> query_embedding) AS v_rank
        FROM scoped_chunks sc
        WHERE sc.embedding IS NOT NULL
        ORDER BY sc.embedding <=> query_embedding
        LIMIT candidate_pool_size
    ),
    lexical_candidates AS (
        SELECT 
            sc.id,
            GREATEST(
                ts_rank_cd(sc.tsv, plainto_tsquery('arabic', query_text)),
                ts_rank_cd(sc.tsv_simple, plainto_tsquery('simple', query_text)),
                ts_rank_cd(sc.tsv_english, plainto_tsquery('english', query_text)),
                ts_rank_cd(sc.tsv_spanish, plainto_tsquery('spanish', query_text)),
                ts_rank_cd(sc.tsv_portuguese, plainto_tsquery('portuguese', query_text))
            )::FLOAT AS l_rank_score,
            ROW_NUMBER() OVER (
                ORDER BY GREATEST(
                    ts_rank_cd(sc.tsv, plainto_tsquery('arabic', query_text)),
                    ts_rank_cd(sc.tsv_simple, plainto_tsquery('simple', query_text)),
                    ts_rank_cd(sc.tsv_english, plainto_tsquery('english', query_text)),
                    ts_rank_cd(sc.tsv_spanish, plainto_tsquery('spanish', query_text)),
                    ts_rank_cd(sc.tsv_portuguese, plainto_tsquery('portuguese', query_text))
                ) DESC
            ) AS l_rank
        FROM scoped_chunks sc
        WHERE sc.tsv @@ plainto_tsquery('arabic', query_text)
           OR sc.tsv_simple @@ plainto_tsquery('simple', query_text)
           OR sc.tsv_english @@ plainto_tsquery('english', query_text)
           OR sc.tsv_spanish @@ plainto_tsquery('spanish', query_text)
           OR sc.tsv_portuguese @@ plainto_tsquery('portuguese', query_text)
        LIMIT candidate_pool_size
    ),
    combined_candidates AS (
        SELECT 
            COALESCE(vc.id, lc.id) AS chunk_id,
            COALESCE(vc.v_sim, 0.0)::FLOAT AS v_similarity,
            COALESCE(lc.l_rank_score, 0.0)::FLOAT AS l_score,
            (
                (vector_weight * (1.0 / (rrf_k + COALESCE(vc.v_rank, candidate_pool_size * 2)))) +
                (keyword_weight * (1.0 / (rrf_k + COALESCE(lc.l_rank, candidate_pool_size * 2)))) +
                CASE 
                    WHEN preferred_languages IS NOT NULL AND sc.c_lang = ANY(preferred_languages) 
                    THEN language_boost 
                    ELSE 0.0 
                END
            )::FLOAT AS final_score
        FROM vector_candidates vc
        FULL OUTER JOIN lexical_candidates lc ON lc.id = vc.id
        JOIN scoped_chunks sc ON sc.id = COALESCE(vc.id, lc.id)
    )
    SELECT 
        sc.id,
        sc.document_id,
        sc.doc_title,
        sc.doc_author,
        sc.w_id,
        sc.w_title,
        sc.e_id,
        sc.e_title,
        sc.e_lang,
        sc.c_lang,
        sc.content,
        sc.chapter_title,
        sc.page_number,
        sc.chunk_index,
        sc.chunk_type,
        sc.parent_chunk_id,
        sc.depth,
        sc.volume_number,
        sc.breadcrumb,
        sc.has_footnotes,
        sc.footnotes_data,
        cc.v_similarity,
        cc.l_score,
        cc.final_score
    FROM combined_candidates cc
    JOIN scoped_chunks sc ON sc.id = cc.chunk_id
    ORDER BY cc.final_score DESC
    LIMIT match_count;
END;
$$;

-- 9. READ-ONLY CANDIDATES RETRIEVAL FOR SEMANTIC CACHE

CREATE OR REPLACE FUNCTION find_semantic_cache_candidates(
    p_embedding vector,
    p_persona text DEFAULT 'standard',
    p_language text DEFAULT 'ar',
    p_format_directive text DEFAULT 'none',
    p_filter_hash text DEFAULT 'ALL',
    p_embedding_model text DEFAULT 'gemini-embedding-2',
    p_corpus_version text DEFAULT 'v1',
    p_schema_version text DEFAULT 'v1',
    p_min_similarity double precision DEFAULT 0.87,
    p_k integer DEFAULT 3
) RETURNS TABLE(
    id uuid,
    query_text text,
    normalized_query text,
    response_text text,
    sources jsonb,
    suggestions jsonb,
    similarity double precision,
    hit_count integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        SET LOCAL hnsw.ef_search = 100;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    RETURN QUERY
    SELECT 
        sqc.id,
        sqc.query_text,
        sqc.normalized_query,
        sqc.response_text,
        sqc.sources,
        sqc.suggestions,
        (1 - (sqc.query_embedding <=> p_embedding))::FLOAT AS similarity,
        sqc.hit_count
    FROM semantic_query_cache sqc
    WHERE sqc.persona = p_persona
      AND sqc.language = p_language
      AND sqc.format_directive = p_format_directive
      AND sqc.filter_hash = p_filter_hash
      AND sqc.embedding_model = p_embedding_model
      AND sqc.corpus_version = p_corpus_version
      AND sqc.schema_version = p_schema_version
      AND sqc.expires_at > NOW()
      AND (1 - (sqc.query_embedding <=> p_embedding)) >= p_min_similarity
    ORDER BY sqc.query_embedding <=> p_embedding ASC
    LIMIT p_k;
END;
$$;
