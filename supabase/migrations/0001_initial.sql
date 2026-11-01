-- ============================================================================
-- ORBIT AI — COMPLETE INITIAL SUPABASE MIGRATION (0001_initial.sql)
-- Directly executable in Supabase Dashboard -> SQL Editor -> New Query
-- Canonical Vector Dimension Contract: vector(128)
-- ============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. TRIGGER FUNCTION (Must exist BEFORE any table triggers reference it)
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- 3. CORE TABLES

-- 3.1 CLIENTS (Tenants)
CREATE TABLE IF NOT EXISTS public.clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    assistant_name TEXT NOT NULL DEFAULT 'Orbit Assistant',
    company_name TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT 'You are a helpful, accurate customer support assistant.',
    fallback_answer TEXT NOT NULL DEFAULT 'I do not have enough verified information in our knowledge base to answer that accurately. Please leave your contact details and our team will assist you.',
    welcome_message TEXT NOT NULL DEFAULT 'Hello! How can I help you today?',
    language TEXT NOT NULL DEFAULT 'en',
    model_override TEXT,
    temperature DOUBLE PRECISION NOT NULL DEFAULT 0.2,
    top_k INTEGER NOT NULL DEFAULT 5,
    min_similarity DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    lead_capture_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notification_email TEXT,
    widget_config JSONB NOT NULL DEFAULT '{
        "primaryColor": "#4f46e5",
        "theme": "dark",
        "logoUrl": "",
        "avatarUrl": "",
        "position": "bottom-right",
        "width": 380,
        "height": 580,
        "radius": 16,
        "launcherIcon": "chat",
        "inputPlaceholder": "Ask a question...",
        "showBranding": true,
        "suggestedQuestions": ["What services do you offer?", "What are your opening hours?", "How can I contact support?"]
    }'::jsonb,
    analytics_config JSONB NOT NULL DEFAULT '{"retentionDays": 90, "trackLatency": true}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_clients_updated_at ON public.clients;
CREATE TRIGGER trg_clients_updated_at
BEFORE UPDATE ON public.clients
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.2 API KEYS
CREATE TABLE IF NOT EXISTS public.api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL DEFAULT 'Primary Widget Key',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_api_keys_updated_at ON public.api_keys;
CREATE TRIGGER trg_api_keys_updated_at
BEFORE UPDATE ON public.api_keys
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.3 DOMAINS (Tenant Domain Allowlist)
CREATE TABLE IF NOT EXISTS public.domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(client_id, domain)
);

-- 3.4 PROMPT VERSIONS
CREATE TABLE IF NOT EXISTS public.prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    system_prompt TEXT NOT NULL,
    fallback_answer TEXT NOT NULL,
    welcome_message TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(client_id, version_number)
);

-- 3.5 CONVERSATIONS
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    preferred_language TEXT,
    summary TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_conversations_updated_at ON public.conversations;
CREATE TRIGGER trg_conversations_updated_at
BEFORE UPDATE ON public.conversations
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.6 MESSAGES
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    intent TEXT NOT NULL DEFAULT 'general',
    language TEXT NOT NULL DEFAULT 'en',
    evidence_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3.7 MESSAGE FEEDBACK (Like / Dislike per Assistant Message)
CREATE TABLE IF NOT EXISTS public.message_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL DEFAULT '',
    rating TEXT NOT NULL CHECK (rating IN ('like', 'dislike')),
    comment TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(client_id, message_id, session_id)
);

DROP TRIGGER IF EXISTS trg_message_feedback_updated_at ON public.message_feedback;
CREATE TRIGGER trg_message_feedback_updated_at
BEFORE UPDATE ON public.message_feedback
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.8 LEADS
CREATE TABLE IF NOT EXISTS public.leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE SET NULL,
    idempotency_key TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    requirement TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'qualified', 'won', 'lost')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(client_id, idempotency_key)
);

DROP TRIGGER IF EXISTS trg_leads_updated_at ON public.leads;
CREATE TRIGGER trg_leads_updated_at
BEFORE UPDATE ON public.leads
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.9 LEAD WORKFLOW
CREATE TABLE IF NOT EXISTS public.lead_workflow (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL UNIQUE REFERENCES public.leads(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'qualified', 'won', 'lost')),
    assignee TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_lead_workflow_updated_at ON public.lead_workflow;
CREATE TRIGGER trg_lead_workflow_updated_at
BEFORE UPDATE ON public.lead_workflow
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.10 USAGE LOGS
CREATE TABLE IF NOT EXISTS public.usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE SET NULL,
    operation TEXT NOT NULL DEFAULT 'chat',
    usage_units INTEGER NOT NULL DEFAULT 1,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    status_code INTEGER NOT NULL DEFAULT 200,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3.11 AUDIT LOGS
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES public.clients(id) ON DELETE SET NULL,
    actor TEXT NOT NULL DEFAULT 'admin',
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3.12 KNOWLEDGE FILES
CREATE TABLE IF NOT EXISTS public.knowledge_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    safe_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'failed')),
    active_version INTEGER NOT NULL DEFAULT 1,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_knowledge_files_updated_at ON public.knowledge_files;
CREATE TRIGGER trg_knowledge_files_updated_at
BEFORE UPDATE ON public.knowledge_files
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.13 KNOWLEDGE VECTORS (Canonical 128-dimension pgvector column)
CREATE TABLE IF NOT EXISTS public.knowledge_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES public.knowledge_files(id) ON DELETE CASCADE,
    source_filename TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3.14 SETTINGS
CREATE TABLE IF NOT EXISTS public.settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_settings_updated_at ON public.settings;
CREATE TRIGGER trg_settings_updated_at
BEFORE UPDATE ON public.settings
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3.15 NOTIFICATIONS (Persistent Outbox)
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
    channel TEXT NOT NULL DEFAULT 'outbox',
    recipient TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON public.notifications;
CREATE TRIGGER trg_notifications_updated_at
BEFORE UPDATE ON public.notifications
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 4. INDEXES
CREATE INDEX IF NOT EXISTS idx_api_keys_client_id ON public.api_keys(client_id);
CREATE INDEX IF NOT EXISTS idx_domains_client_id_domain ON public.domains(client_id, domain);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_client_id ON public.prompt_versions(client_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_client_session ON public.conversations(client_id, session_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON public.messages(conversation_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_messages_client_created ON public.messages(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_message_feedback_client_conv ON public.message_feedback(client_id, conversation_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_message_id ON public.message_feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_leads_client_created ON public.leads(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_workflow_client_id ON public.lead_workflow(client_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_client_created ON public.usage_logs(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON public.audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_files_client_id ON public.knowledge_files(client_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_client_active ON public.knowledge_vectors(client_id, is_active, source_id, version);
CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_embedding_hnsw ON public.knowledge_vectors USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_notifications_status_created ON public.notifications(status, created_at ASC);

-- 5. VECTOR SEARCH RPC FUNCTION (Strict 128-Dim & Tenant-Isolated Contract)
CREATE OR REPLACE FUNCTION public.match_knowledge_vectors(
    query_embedding vector(128),
    match_client_id UUID,
    match_threshold DOUBLE PRECISION DEFAULT 0.20,
    match_count INTEGER DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    source_id UUID,
    source_filename TEXT,
    chunk_index INTEGER,
    content TEXT,
    version INTEGER,
    similarity DOUBLE PRECISION
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        kv.id,
        kv.source_id,
        kv.source_filename,
        kv.chunk_index,
        kv.content,
        kv.version,
        1 - (kv.embedding <=> query_embedding) AS similarity
    FROM public.knowledge_vectors kv
    INNER JOIN public.knowledge_files kf
        ON kf.id = kv.source_id
        AND kf.client_id = kv.client_id
    WHERE kv.client_id = match_client_id
      AND kv.is_active = TRUE
      AND kf.status = 'ready'
      AND kv.version = kf.active_version
      AND (1 - (kv.embedding <=> query_embedding)) >= match_threshold
    ORDER BY kv.embedding <=> query_embedding ASC
    LIMIT GREATEST(match_count, 1);
$$;

-- 6. ROW LEVEL SECURITY (RLS)
ALTER TABLE public.clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.message_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_workflow ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_vectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Guarded Tenant Isolation Policies using JWT claim `app_tenant_id`
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'clients' AND policyname = 'tenant_isolation_clients') THEN
        CREATE POLICY tenant_isolation_clients ON public.clients
            FOR ALL TO authenticated
            USING (id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'api_keys' AND policyname = 'tenant_isolation_api_keys') THEN
        CREATE POLICY tenant_isolation_api_keys ON public.api_keys
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'domains' AND policyname = 'tenant_isolation_domains') THEN
        CREATE POLICY tenant_isolation_domains ON public.domains
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'prompt_versions' AND policyname = 'tenant_isolation_prompt_versions') THEN
        CREATE POLICY tenant_isolation_prompt_versions ON public.prompt_versions
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'conversations' AND policyname = 'tenant_isolation_conversations') THEN
        CREATE POLICY tenant_isolation_conversations ON public.conversations
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'messages' AND policyname = 'tenant_isolation_messages') THEN
        CREATE POLICY tenant_isolation_messages ON public.messages
            FOR ALL TO authenticated
            USING (
                client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', '')
                AND EXISTS (
                    SELECT 1 FROM public.conversations c
                    WHERE c.id = messages.conversation_id
                      AND c.client_id = messages.client_id
                )
            )
            WITH CHECK (
                client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', '')
            );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'message_feedback' AND policyname = 'tenant_isolation_message_feedback') THEN
        CREATE POLICY tenant_isolation_message_feedback ON public.message_feedback
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'leads' AND policyname = 'tenant_isolation_leads') THEN
        CREATE POLICY tenant_isolation_leads ON public.leads
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'lead_workflow' AND policyname = 'tenant_isolation_lead_workflow') THEN
        CREATE POLICY tenant_isolation_lead_workflow ON public.lead_workflow
            FOR ALL TO authenticated
            USING (
                client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', '')
                AND EXISTS (
                    SELECT 1 FROM public.leads l
                    WHERE l.id = lead_workflow.lead_id
                      AND l.client_id = lead_workflow.client_id
                )
            )
            WITH CHECK (
                client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', '')
            );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'usage_logs' AND policyname = 'tenant_isolation_usage_logs') THEN
        CREATE POLICY tenant_isolation_usage_logs ON public.usage_logs
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'knowledge_files' AND policyname = 'tenant_isolation_knowledge_files') THEN
        CREATE POLICY tenant_isolation_knowledge_files ON public.knowledge_files
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'knowledge_vectors' AND policyname = 'tenant_isolation_knowledge_vectors') THEN
        CREATE POLICY tenant_isolation_knowledge_vectors ON public.knowledge_vectors
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'notifications' AND policyname = 'tenant_isolation_notifications') THEN
        CREATE POLICY tenant_isolation_notifications ON public.notifications
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;
END
$$;

-- 7. SUPABASE PRIVATE STORAGE BUCKET (`knowledge`)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'storage' AND table_name = 'buckets'
    ) THEN
        INSERT INTO storage.buckets (id, name, public)
        VALUES ('knowledge', 'knowledge', FALSE)
        ON CONFLICT (id) DO UPDATE SET public = FALSE;
    END IF;
END
$$;
