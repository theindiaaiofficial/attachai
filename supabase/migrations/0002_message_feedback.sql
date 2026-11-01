-- ============================================================================
-- ORBIT AI — ADDITIVE MESSAGE FEEDBACK & CONVERSATION MEMORY MIGRATION
-- (0002_message_feedback.sql)
-- Safe to run on existing installations and after 0001_initial.sql
-- ============================================================================

-- Ensure set_updated_at() exists before trigger creation
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Ensure conversation language & summary columns exist on older installations
ALTER TABLE IF EXISTS public.conversations
    ADD COLUMN IF NOT EXISTS preferred_language TEXT,
    ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS message_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS public.messages
    ADD COLUMN IF NOT EXISTS intent TEXT NOT NULL DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en',
    ADD COLUMN IF NOT EXISTS evidence_state TEXT NOT NULL DEFAULT 'UNKNOWN';

-- Create message_feedback table if absent
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

CREATE INDEX IF NOT EXISTS idx_message_feedback_client_conv ON public.message_feedback(client_id, conversation_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_message_id ON public.message_feedback(message_id);

ALTER TABLE public.message_feedback ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'message_feedback'
          AND policyname = 'tenant_isolation_message_feedback'
    ) THEN
        CREATE POLICY tenant_isolation_message_feedback ON public.message_feedback
            FOR ALL TO authenticated
            USING (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''))
            WITH CHECK (client_id::text = coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'app_tenant_id', ''));
    END IF;
END
$$;
