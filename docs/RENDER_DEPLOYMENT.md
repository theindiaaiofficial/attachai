# Orbit AI — Render Deployment Guide

Orbit AI deploys natively on Render's Python runtime using the included `render.yaml` Blueprint. No Node.js runtime or separate frontend hosting is required.

## Deployment Steps

1. Push the repository to GitHub.
2. In the Render Dashboard, click **New + → Blueprint** (or **Web Service**) and connect your GitHub repository.
3. Render automatically detects `render.yaml` with:
   - **Runtime**: `python` (pinned via `.python-version`)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/ready`
4. Populate the secret environment variables (`sync: false` in `render.yaml`):
   - `ADMIN_API_KEY`
   - `ALLOWED_ORIGINS`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `LLM_PROVIDER_NAME`
   - `LLM_BASE_URL`
   - `LLM_API_KEY`
   - `LLM_MODEL`
5. Deploy the service and verify `/ready` returns HTTP 200.
6. Open `https://YOUR-RENDER-SERVICE.onrender.com/admin` to sign in and manage tenants.
