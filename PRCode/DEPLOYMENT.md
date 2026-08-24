# PRGuard Deployment Guide

## Architecture
- Frontend: Vercel (Vite static app)
- Backend: Render or Railway (FastAPI)
- Database: PostgreSQL
- Cache/Queue: Redis

## Required Backend Environment Variables
- ENVIRONMENT=production
- PORT=8000
- APP_URL=https://<your-backend-domain>
- FRONTEND_URL=https://<your-frontend-domain>
- CORS_ORIGINS=https://<your-frontend-domain>
- SECRET_KEY=<long-random-secret>
- DATABASE_URL=postgresql://<user>:<password>@<your-neon-pooler-host>/<db>?sslmode=require&channel_binding=require
- REDIS_URL=redis://:<password>@<host>:<port>
- GITHUB_CLIENT_ID=<github-oauth-client-id>
- GITHUB_CLIENT_SECRET=<github-oauth-client-secret>
- GITHUB_WEBHOOK_SECRET=<github-webhook-secret>
- GITHUB_APP_ID=<github-app-id>
- GITHUB_PRIVATE_KEY_PATH=./private-key.pem
- ADMIN_USERNAME=<bootstrap-admin-username>
- ADMIN_PASSWORD=<bootstrap-admin-password>
- ADMIN_USERS=<comma-separated-github-logins>
- ADMIN_EMAIL=<admin-email>

## Optional Backend Environment Variables
- OPENAI_API_KEY=<optional global fallback key>
- ANTHROPIC_API_KEY=<optional global fallback key>
- GEMINI_API_KEY=<optional global fallback key>
- MODEL_PROVIDER=gemini
- MODEL_NAME=gemini-2.5-flash
- CHAT_ENABLE_RAG=false
- PRELOAD_RAG_ON_STARTUP=false

## Required Frontend Environment Variables
- VITE_API_BASE_URL=https://<your-backend-domain>
- VITE_GITHUB_CLIENT_ID=<github-oauth-client-id>

## Frontend Deploy Steps (Vercel)
1. Create project in Vercel and connect the repository.
2. Set Root Directory to frontend.
3. Set build command to npm run build.
4. Set output directory to dist.
5. Configure VITE_API_BASE_URL and VITE_GITHUB_CLIENT_ID in Vercel env settings.
6. Deploy.

## Backend Deploy Steps (Render/Railway)
1. Create a Web Service from this repository.
2. Set Root Directory to backend.
3. Start command: python run.py
4. Add all backend env vars listed above. DATABASE_URL is mandatory and startup fails if it is missing.
5. Attach managed PostgreSQL and Redis.
6. Deploy and confirm https://<backend>/health returns status ok.

## Vercel/Render Notes
1. If backend is hosted on Render/Railway, set DATABASE_URL in that backend service (not only in frontend Vercel).
2. If backend is hosted as a Vercel serverless function, set DATABASE_URL in Vercel project environment variables for Production, Preview, and Development.

## Production Checks
1. Login cookie should be secure and cross-site compatible (SameSite=None, Secure=true).
2. Admin login must use dedicated credentials at /admin/login and issue httpOnly admin_session cookie.
3. CORS must include only trusted frontend domains.
4. API keys are encrypted server-side per user and never stored in browser storage.
5. Frontend requests should use VITE_API_BASE_URL, not localhost.
6. Verify /admin/users, /admin/user/{id}, /admin/api-keys-status, /admin/logs for runtime visibility.
