# Orbit AI — Architecture & Data Flow

Orbit AI is a centralized, multi-tenant AI customer-support SaaS platform built with Python, FastAPI, Supabase PostgreSQL, pgvector (`vector(128)`), and a vanilla JavaScript embeddable customer widget.

## 1. Customer Chat, Orchestration & Grounded RAG Flow

```mermaid
flowchart TD
    CW[Customer Website] --> EW[Embeddable Widget\nstatic/js/widget.js]
    EW --> PUB[FastAPI Public API\napp/api/public.py]
    PUB --> AUTH[Tenant Authentication & Domain Check\napp/middleware/authentication.py\napp/services/clients.py]
    AUTH --> CHAT[Chat Orchestration Service\napp/services/chat.py]
    CHAT --> CONV[Conversation & Language Service\napp/services/conversations.py]
    CONV -->|Conversational Intent:\ngreeting / identity / language_switch / memory_query / summary| PROMPT[Prompt Builder\napp/services/prompts.py]
    CONV -->|Business or Mixed Query| RAG[Advanced Multi-Query RAG Pipeline\napp/services/advanced_rag.py]
    RAG --> EMB[Embedding Provider\napp/providers/embeddings.py]
    RAG --> VEC[Supabase pgvector RPC\napp/providers/vector.py\nmatch_knowledge_vectors]
    RAG --> LEX[Paginated Lexical Retrieval & RRF Fusion\napp/services/advanced_rag.py]
    VEC --> PROMPT
    LEX --> PROMPT
    PROMPT --> LLM[LLM Provider\napp/providers/llm.py]
    LLM --> GND[Evidence-Aware Grounding Validator\napp/services/grounding.py]
    GND --> REPO[Conversation Repository\napp/repositories/supabase.py & sqlite.py]
    REPO --> ANS[Validated Answer + Sources + Message ID]
    ANS --> EW
```

## 2. Safe Versioned Knowledge Ingestion Flow

```mermaid
flowchart TD
    ADM[Admin Dashboard\napp/templates/dashboard.html] --> KAPI[Admin Knowledge Route\napp/api/admin.py]
    KAPI --> KSVC[Knowledge Service\napp/services/knowledge.py]
    KSVC --> VAL[Upload Validator\napp/utils/validators.py]
    VAL --> PARSE[Document Parser PDF/DOCX/CSV/MD/TXT\napp/services/parser.py]
    PARSE --> STORE[Private Bucket Storage\napp/providers/storage.py]
    PARSE --> CHUNK[Paragraph-Aware Chunker\napp/utils/chunking.py]
    CHUNK --> EMB2[128-Dim Embedding Provider\napp/providers/embeddings.py]
    EMB2 --> STAGE[Stage Vector Version\napp/providers/vector.py]
    STAGE --> VERIFY[Verify Staged Chunk Count]
    VERIFY -->|Verified| ACT[Activate New Version & Clean Old Version]
    VERIFY -->|Failed| KEEP[Preserve Previous Active Index Version]
```

## 3. Idempotent Lead Capture & Outbox Notification Flow

```mermaid
flowchart TD
    WLEAD[Customer Widget Lead Form\nstatic/js/widget.js] --> LAPI[POST /v1/leads\napp/api/public.py]
    LAPI --> LSVC[Lead Service\napp/services/leads.py]
    LSVC --> IDEM[Idempotency Check\nclient_id + idempotency_key]
    IDEM --> DBLEAD[Persist Lead & Lead Workflow\napp/repositories/supabase.py]
    DBLEAD --> OUTBOX[Persist Notification Outbox Record\napp/providers/notifications.py]
    OUTBOX --> DELIV[Deliver via Supabase Outbox / Optional SMTP]
```
