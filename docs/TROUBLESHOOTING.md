# Orbit AI — Troubleshooting Guide

## 1. `/ready` returns HTTP 503
- **Cause**: The Supabase migration (`supabase/migrations/0001_initial.sql`) has not been executed yet, or `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` is invalid.
- **Resolution**: Execute `supabase/migrations/0001_initial.sql` in the Supabase SQL Editor and verify the `knowledge` bucket and `match_knowledge_vectors` RPC exist.

## 2. Vector Dimension Mismatch at Startup
- **Cause**: `EMBEDDING_DIMENSIONS` and `SUPABASE_VECTOR_DIMENSIONS` do not match, or `EMBEDDING_PROVIDER=local` is paired with a dimension other than `128`.
- **Resolution**: Keep both `EMBEDDING_DIMENSIONS=128` and `SUPABASE_VECTOR_DIMENSIONS=128` to match `vector(128)` in `0001_initial.sql`.

## 3. Widget Returns HTTP 403 (`Origin is not in the tenant's domain allowlist`)
- **Cause**: The customer website hostname is not listed in the tenant's allowed domains.
- **Resolution**: In the Admin Dashboard, add the customer website domain to the tenant's domain allowlist.

## 4. LLM Upstream 503 / Circuit Breaker Cooldown
- **Cause**: The configured OpenAI-compatible LLM provider returned repeated 429/5xx errors or timed out.
- **Resolution**: Verify `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. Orbit AI never substitutes fake local answers when a production LLM fails.
