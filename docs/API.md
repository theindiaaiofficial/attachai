# Orbit AI — Public, Admin & System API Reference

## 1. Public Widget APIs (Authenticated via `x-api-key`)

### `GET /v1/config`
Returns safe, public widget configuration for the authenticated tenant. Never exposes raw API keys, key hashes, admin secrets, provider keys, or system prompts.

### `POST /v1/chat`
Request body:
```json
{
  "message": "What services do you offer?",
  "sessionId": "OPTIONAL_SESSION_ID",
  "conversationId": "OPTIONAL_UUID"
}
```
Response body:
```json
{
  "conversationId": "UUID",
  "sessionId": "SESSION_ID",
  "messageId": "UUID",
  "answer": "Validated assistant response",
  "intent": "business_query",
  "language": "en",
  "evidenceState": "SUPPORTED",
  "sources": [],
  "latencyMs": 18
}
```

### `POST /v1/chat/stream`
Server-Sent Events (`text/event-stream`) endpoint using the exact same orchestration, language detection, memory, RAG retrieval, and grounding validation as `POST /v1/chat`. Buffers and validates untrusted model output before emitting `event: token` and `event: done` frames.

### `POST /v1/feedback`
Persists tenant-scoped assistant message feedback (`like` or `dislike`) idempotently per `(client_id, message_id, session_id)`.
```json
{
  "conversationId": "UUID",
  "messageId": "UUID",
  "sessionId": "SESSION_ID",
  "rating": "like",
  "comment": "Optional feedback note"
}
```

### `POST /v1/leads`
Idempotent customer lead submission linked to the authenticated tenant and optional conversation.

---

## 2. Administrative APIs (Authenticated via `x-admin-api-key` or Session Cookie + `x-csrf-token`)

- `POST /admin/api/login` — Exchange `ADMIN_API_KEY` for a signed HttpOnly session cookie and CSRF token.
- `GET /admin/api/overview` — Global KPIs, provider diagnostics, and recent audit logs.
- `GET /admin/api/tenants` — List all tenants.
- `POST /admin/api/tenants` — Create a tenant and generate its initial API key.
- `GET /admin/api/tenants/{client_id}` — Retrieve tenant detail, API keys, prompt versions, and knowledge files.
- `PATCH /admin/api/tenants/{client_id}` — Update tenant configuration, retrieval settings, or widget theme.
- `POST /admin/api/tenants/{client_id}/duplicate` — Duplicate a tenant with an independent slug and API key.
- `DELETE /admin/api/tenants/{client_id}` — Delete a tenant and clean up storage objects, vectors, and records.
- `POST /admin/api/tenants/{client_id}/rotate-key` — Rotate the tenant's public API key.
- `POST /admin/api/tenants/{client_id}/domains` & `DELETE /admin/api/tenants/{client_id}/domains` — Manage domain allowlist.
- `POST /admin/api/tenants/{client_id}/prompts` & `POST /admin/api/tenants/{client_id}/prompts/restore` — Save and restore prompt versions.
- `POST /admin/api/tenants/{client_id}/knowledge` — Upload and index a document (`PDF`, `DOCX`, `CSV`, `MD`, `TXT`).
- `POST /admin/api/tenants/{client_id}/knowledge/{file_id}/rebuild` — Safely re-index a stored document.
- `DELETE /admin/api/tenants/{client_id}/knowledge/{file_id}` — Delete a document and its vectors.
- `GET /admin/api/conversations` & `GET /admin/api/conversations/{conversation_id}` — Inspect conversations, messages, and feedback.
- `GET /admin/api/leads`, `PATCH /admin/api/leads/{lead_id}`, `GET /admin/api/leads/export` — Manage and export leads.
- `GET /admin/api/analytics` — Retrieve persisted daily usage, latency, and feedback metrics.

---

## 3. System Endpoints

- `GET /health` — Lightweight application liveness check.
- `GET /ready` — Readiness probe verifying database connectivity, schema, storage, and vector dimension contract.
- `GET /metrics` — Admin-protected operational metrics.
