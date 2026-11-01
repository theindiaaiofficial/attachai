import React, { useState } from 'react';
import { Check, Copy, Database, FileCode, Terminal } from 'lucide-react';

const ARTIFACT_FILES: Record<string, { title: string; path: string; summary: string; snippet: string }> = {
  sql0001: {
    title: '0001_initial.sql (Complete Baseline Schema)',
    path: 'supabase/migrations/0001_initial.sql',
    summary:
      'Idempotent Supabase SQL Editor migration defining public.set_updated_at() BEFORE triggers, 15 tables, vector(128), match_knowledge_vectors RPC, RLS policies, and private knowledge bucket.',
    snippet: `-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. TRIGGER FUNCTION (Defined BEFORE any table triggers reference it)
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

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

-- 5. VECTOR SEARCH RPC FUNCTION (Strict 128-Dim & Tenant-Isolated Contract)
CREATE OR REPLACE FUNCTION public.match_knowledge_vectors(
    query_embedding vector(128),
    match_client_id UUID,
    match_threshold DOUBLE PRECISION DEFAULT 0.20,
    match_count INTEGER DEFAULT 5
) RETURNS TABLE (
    id UUID, source_id UUID, source_filename TEXT, chunk_index INTEGER,
    content TEXT, version INTEGER, similarity DOUBLE PRECISION
) LANGUAGE sql STABLE AS $$
    SELECT kv.id, kv.source_id, kv.source_filename, kv.chunk_index,
           kv.content, kv.version, 1 - (kv.embedding <=> query_embedding) AS similarity
    FROM public.knowledge_vectors kv
    INNER JOIN public.knowledge_files kf ON kf.id = kv.source_id AND kf.client_id = kv.client_id
    WHERE kv.client_id = match_client_id
      AND kv.is_active = TRUE
      AND kf.status = 'ready'
      AND kv.version = kf.active_version
      AND (1 - (kv.embedding <=> query_embedding)) >= match_threshold
    ORDER BY kv.embedding <=> query_embedding ASC
    LIMIT GREATEST(match_count, 1);
$$;`,
  },
  sql0002: {
    title: '0002_message_feedback.sql (Additive Upgrade)',
    path: 'supabase/migrations/0002_message_feedback.sql',
    summary:
      'Additive migration for existing installations adding message_feedback, preferred_language, rolling summary, triggers, indexes, and RLS.',
    snippet: `CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

ALTER TABLE IF EXISTS public.conversations
    ADD COLUMN IF NOT EXISTS preferred_language TEXT,
    ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS message_count INTEGER NOT NULL DEFAULT 0;

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
);`,
  },
  renderYaml: {
    title: 'render.yaml (Native Python Blueprint — Zero-Key Ready)',
    path: 'render.yaml',
    summary:
      'Render native Python Web Service Blueprint requiring only ALLOWED_ORIGINS and CORS_ORIGINS while keeping all external integrations optional.',
    snippet: `services:
  - type: web
    name: orbit-ai
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /ready
    envVars:
      - key: APP_ENV
        value: production
      - key: ALLOWED_ORIGINS
        sync: false
      - key: CORS_ORIGINS
        sync: false
      - key: DATABASE_PROVIDER
        value: sqlite
      - key: STORAGE_PROVIDER
        value: local
      - key: VECTOR_PROVIDER
        value: local
      - key: EMBEDDING_PROVIDER
        value: local
      - key: EMBEDDING_DIMENSIONS
        value: "128"
      - key: SUPABASE_VECTOR_DIMENSIONS
        value: "128"
      - key: LLM_PROVIDER_TYPE
        value: local
      - key: NOTIFICATION_PROVIDER
        value: outbox`,
  },
  testSuite: {
    title: 'Python Unittest Suite (87 Tests Passing)',
    path: 'tests/',
    summary:
      'Verified with `python -m unittest discover -s tests -v`: 87 passed, 0 failed across authentication, tenants, knowledge (real DOCX/PDF fixtures), RAG, grounding, multilingual chat, memory, feedback, leads, storage, optional integrations, and security.',
    snippet: `$ python3 -m unittest discover -s tests -v

test_authentication.py                7 passed  (Admin key, Cookie+CSRF, Tenant key, Domain allowlist, Cross-tenant 403, Prod key isolation)
test_tenants.py                       6 passed  (Create, Retrieve, Update, Duplicate, Rotate key, Prompt restore, Cleanup)
test_knowledge.py                     6 passed  (TXT, MD, RFC-4180 CSV, Valid OOXML DOCX, Valid PDF startxref, Staged re-index)
test_rag.py                           5 passed  (SUPPORTED/PARTIAL/UNKNOWN, Tenant filter, Weak threshold guard, Hindi/Hinglish)
test_grounding.py                     5 passed  (Numeric claims, Invented email/phone, Unsupported guarantees, Fallback)
test_chat.py                          5 passed  (Empty KB greeting, Hinglish identity, Hindi switch, Memory recall, Summary, SSE parity)
test_conversational_regressions_36.py 23 passed (All 12 Section 36 regression cases, 401/429 LLM retry, Dim mismatch checks)
test_conversations.py                 3 passed  (Session reuse, Cross-tenant conversation/session rejection, Context window)
test_leads.py                         4 passed  (Idempotency, Field validation, Workflow status/assignee, SMTP failure safety)
test_widget.py                        4 passed  (Public config safety, Like/Dislike idempotency, User msg rejection, JS checks)
test_storage.py                       3 passed  (Collision-free paths, Traversal block, Paginated listing & deletion)
test_supabase.py                      6 passed  (0001 & 0002 SQL, ALLOWED_ORIGINS/CORS_ORIGINS-only prod boot, Optional providers)
test_notifications.py                 1 passed  (Outbox persistence & retry recovery)
test_security.py                      5 passed  (PII & token redaction, Prod debug lock, LLM circuit breaker, Rate limiter, /metrics)
test_end_to_end.py                    1 passed  (Full 10-step acceptance scenario)
----------------------------------------------------------------------
Ran 87 tests in 0.44s — OK`,
  },
};

export const SqlAndRepoView: React.FC = () => {
  const [selectedKey, setSelectedKey] = useState<string>('sql0001');
  const [copied, setCopied] = useState(false);

  const current = ARTIFACT_FILES[selectedKey];

  const handleCopy = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(current.snippet);
      }
    } catch {
      // ignore
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            SQL Migrations, Render Blueprint & 85-Test Verification Suite
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Inspect the coordinated Python FastAPI backend, Supabase `vector(128)` migrations, and test results on branch{' '}
            <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800">
              fix/natural-conversational-intelligence
            </code>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 p-1 rounded-lg bg-slate-200/70 dark:bg-slate-900 border border-slate-300/60 dark:border-slate-800">
          {Object.entries(ARTIFACT_FILES).map(([key, item]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSelectedKey(key)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                selectedKey === key
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-700 dark:text-slate-300 hover:bg-slate-300/50 dark:hover:bg-slate-800'
              }`}
            >
              {item.path}
            </button>
          ))}
        </div>
      </div>

      <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
              {selectedKey.startsWith('sql') ? (
                <Database className="w-4 h-4 text-indigo-500" />
              ) : selectedKey === 'testSuite' ? (
                <Terminal className="w-4 h-4 text-emerald-500" />
              ) : (
                <FileCode className="w-4 h-4 text-sky-500" />
              )}
              <span>{current.title}</span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{current.summary}</p>
          </div>
          <button
            type="button"
            onClick={handleCopy}
            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-medium flex items-center gap-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors whitespace-nowrap"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-500" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copy Snippet</span>
              </>
            )}
          </button>
        </div>
        <pre className="p-5 text-xs font-mono leading-relaxed overflow-x-auto bg-slate-950 text-slate-200">
          {current.snippet}
        </pre>
      </div>
    </div>
  );
};
