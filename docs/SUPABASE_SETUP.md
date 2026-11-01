# Orbit AI — Supabase Setup Guide

Follow these steps to configure Supabase for Orbit AI:

1. **Create a Supabase Project**: Sign in to Supabase and create a new project.
2. **Open SQL Editor**: Navigate to **SQL Editor → New Query**.
3. **Run the Baseline Migration**:
   - Open `supabase/migrations/0001_initial.sql` from this repository.
   - Copy the entire file contents, paste into the Supabase SQL Editor, and click **Run**.
   - *(If upgrading an existing installation that already ran an older `0001_initial.sql`, run `supabase/migrations/0002_message_feedback.sql` as well).*
4. **Verify Tables in Table Editor**:
   - Confirm that `clients`, `api_keys`, `domains`, `prompt_versions`, `conversations`, `messages`, `message_feedback`, `leads`, `lead_workflow`, `usage_logs`, `audit_logs`, `knowledge_files`, `knowledge_vectors`, `settings`, and `notifications` exist.
5. **Verify Private Storage Bucket**:
   - Open **Storage** in Supabase Dashboard and confirm the `knowledge` bucket exists and is marked **Private** (`public = false`).
6. **Verify pgvector & RPC**:
   - Confirm the `vector` extension is enabled and `public.match_knowledge_vectors` accepts `vector(128)`.
7. **Copy Credentials to Render**:
   - From **Project Settings → API**, copy your **Project URL** (`SUPABASE_URL`) and **service_role secret** (`SUPABASE_SERVICE_ROLE_KEY`).
   - **Security Warning**: The `service_role` key is strictly a backend secret. Never place it in browser JavaScript, HTML, or public git commits.
