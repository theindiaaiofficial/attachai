# Orbit AI — Environment Variable Reference

## Required in Production (`APP_ENV=production`)

| Variable | Description |
|---|---|
| `APP_ENV` | `production` (falls back to `NODE_ENV` if `APP_ENV` is unset) |
| `ADMIN_API_KEY` | Strong administrator secret required for `/admin/api/*` and `/metrics` |
| `ALLOWED_ORIGINS` | Comma-separated trusted origins (takes precedence over legacy `CORS_ORIGINS`) |
| `DATABASE_PROVIDER` | `supabase` (production) or `sqlite` (local dev/tests) |
| `STORAGE_PROVIDER` | `supabase` (production) or `local` (local dev/tests) |
| `VECTOR_PROVIDER` | `supabase` (production), `local`, or optional `qdrant` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only Supabase service-role key (never exposed to clients) |
| `SUPABASE_STORAGE_BUCKET` | `knowledge` (private bucket) |
| `SUPABASE_VECTOR_DIMENSIONS` | `128` (must match `EMBEDDING_DIMENSIONS` and SQL `vector(128)`) |
| `LLM_PROVIDER_TYPE` | `openai-compatible` (production) or `local` (isolated dev/tests) |
| `LLM_PROVIDER_NAME` | Provider identifier (e.g., `openai`, `groq`, `openrouter`) |
| `LLM_BASE_URL` | OpenAI-compatible base URL |
| `LLM_API_KEY` | Server-only LLM API credential |
| `LLM_MODEL` | Chat model identifier |
| `NOTIFICATION_PROVIDER` | `supabase` (production default), `outbox`, or optional `smtp` |

## Optional Integrations (Disabled by Default — Never Required to Build or Start)

- **External Embeddings**: `EMBEDDING_PROVIDER=local` (default 128-dim deterministic embeddings). Set `EMBEDDING_PROVIDER=openai-compatible` with `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, and `EMBEDDING_DIMENSIONS` only if using an external embedding API.
- **Qdrant**: Only used when `VECTOR_PROVIDER=qdrant` and `QDRANT_URL` is provided.
- **SMTP**: Only used when `NOTIFICATION_PROVIDER=smtp` and `SMTP_HOST` / `SMTP_FROM` are provided.
- **TTS**: `TTS_API_KEY` is recognized as server-only and remains disabled unless `TTS_PROVIDER`, `TTS_BASE_URL`, and `TTS_MODEL` are also configured.
- **RAG Diagnostics**: `ORBIT_RAG_DIAGNOSTICS=0` (default). Temporary debug flags (`ORBIT_TEMP_DEBUG_*`) are forced off in production.
