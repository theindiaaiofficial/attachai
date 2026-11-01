# Orbit AI — Multi-Tenant AI Customer Support & Grounded RAG SaaS Platform

Orbit AI is a production-ready, multi-tenant customer support SaaS platform built with **Python**, **FastAPI**, **Supabase (PostgreSQL + pgvector + private Storage)**, and a lightweight **vanilla JavaScript embeddable chat widget**.

## Key Capabilities

- **Strict Multi-Tenant Isolation**: Independent API credentials (`SHA-256` hashed), domain allowlists, system prompts, versioned prompt history, knowledge documents, 128-dim vector indexes, conversations, leads, notifications, widget themes, and analytics per tenant.
- **Natural, LLM-First Conversational Intelligence**: Separates conversational intents (`greeting`, `identity`, `language_switch`, `memory_query`, `summary`) from business RAG queries so greetings, identity questions, and memory recall work naturally without false RAG fallbacks.
- **Dynamic Multilingual Support**: Supports English, Devanagari Hindi (`हिंदी`), Roman Hindi / Hinglish, Spanish, and French, including mid-conversation language switches (`"Hindi mein likho"` ↔ `"Reply in English"`).
- **Persistent Multi-Turn Memory & Real Summaries**: Tenant-isolated session & conversation history, pronoun/follow-up resolution (`"uske baare mein"`, `"that"`), prior-question recall (`"Humne tumse pahle kya pucha tha?"`), and factual conversation summaries.
- **Advanced Grounded RAG Engine**: Safe staged versioned ingestion for `PDF`, `DOCX`, `CSV`, `Markdown`, and `TXT`, 128-dimensional embeddings, hybrid dense + paginated lexical search with Reciprocal Rank Fusion (RRF), explicit evidence states (`SUPPORTED`, `PARTIAL`, `UNKNOWN`), and numeric/contact/guarantee grounding validation.
- **Premium Embeddable Widget**: Single-script-tag installation with per-message **Like/Dislike feedback** persisted server-side, **Copy** (Clipboard API + fallback), **Share** (Web Share API + fallback), dark/light themes, and idempotent **Lead Capture**.

## Quick Start (Local Development & Automated Tests)

```powershell
# Run the complete automated test suite (85 tests)
python -m unittest discover -s tests -v

# Start the FastAPI server locally (when uvicorn is installed)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Documentation

- [Architecture & Mermaid Diagrams](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Database & Migration Contract](docs/DATABASE.md)
- [Supabase Setup Guide](docs/SUPABASE_SETUP.md)
- [Render Deployment Guide](docs/RENDER_DEPLOYMENT.md)
- [Environment Variables Reference](docs/ENV_VARIABLES.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
