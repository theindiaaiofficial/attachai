# Orbit AI — Database Schema & Migration Contract

## Canonical Tables (`public`)

1. `clients` — Tenant identity, assistant name, system prompt, fallback answer, retrieval thresholds, and `widget_config` JSONB.
2. `api_keys` — SHA-256 key hashes (`key_hash`), prefix, label, and enabled flag (raw keys are never stored).
3. `domains` — Allowed website origins/domains per tenant.
4. `prompt_versions` — Versioned system prompts, fallback answers, and welcome messages per tenant.
5. `conversations` — Tenant-scoped customer sessions, `preferred_language`, rolling `summary`, and `message_count`.
6. `messages` — User and assistant messages with `intent`, `language`, `evidence_state`, `sources`, and `latency_ms`.
7. `message_feedback` — Tenant-scoped `like`/`dislike` feedback linked to `messages`, `conversations`, and `clients`.
8. `leads` — Idempotent customer lead records (`UNIQUE(client_id, idempotency_key)`).
9. `lead_workflow` — Lead status (`new`, `contacted`, `qualified`, `won`, `lost`), assignee, and internal notes.
10. `usage_logs` — Per-request operation, usage units, and latency telemetry.
11. `audit_logs` — Administrative and security audit events.
12. `knowledge_files` — Uploaded document metadata, storage path, status (`processing`, `ready`, `failed`), and `active_version`.
13. `knowledge_vectors` — Chunk text, version, active flag, and `embedding vector(128)`.
14. `settings` — Safe application settings.
15. `notifications` — Persistent notification outbox with delivery status, attempts, and error tracking.

## Migration Execution Order

- **Fresh Installations**: Run `supabase/migrations/0001_initial.sql` in the Supabase SQL Editor. It includes all 15 tables, `public.set_updated_at()` defined before triggers, `match_knowledge_vectors`, RLS policies, and the private `knowledge` bucket.
- **Existing Installations Upgrading**: Run `supabase/migrations/0002_message_feedback.sql` in the Supabase SQL Editor to add `message_feedback` and conversation language/memory columns non-destructively.
