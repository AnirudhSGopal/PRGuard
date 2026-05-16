# Production Deployment Platform Configuration

## Vercel (Frontend: React + Vite)

### 1. Project Setup
```bash
# In Vercel dashboard or CLI:
vercel link  # Connect to your GitHub repo

# Verify it's set to:
# Framework: Vite
# Build Command: npm run build
# Output Directory: dist
```

### 2. Environment Variables (CRITICAL)
Go to **Vercel Dashboard → [Your Project] → Settings → Environment Variables**

Add these variables:

| Name | Value | Environments |
|------|-------|-------------|
| `VITE_API_BASE_URL` | `https://api.prguard.railway.app` | Production, Preview, Development |
| `VITE_API_PROXY_TARGET` | (empty) | Development |
| `NODE_ENV` | `production` | Production |

**⚠️ IMPORTANT:** After setting these, go to **Deployments** and click **Redeploy** on the latest commit. Vite bakes these into the build.

### 3. Deployment Trigger
```bash
git push origin main
# OR manually redeploy in Vercel dashboard
```

### 4. Verify Frontend
```bash
curl https://prguard.vercel.app
# Should return HTML with built-in API_URL
```

---

## Railway (Backend: FastAPI + Python)

### 1. Create Service
1. Go to railway.app → New Project
2. Choose "GitHub Repo" 
3. Select your repo → Deploy
4. Railway auto-detects Python + creates service

### 2. Environment Variables (CRITICAL)
Go to **Railway Dashboard → [Your Service] → Variables**

Add ALL these variables:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require

# URLs - MUST match production URLs
APP_URL=https://api.prguard.railway.app
FRONTEND_URL=https://prguard.vercel.app

# GitHub OAuth - Get from GitHub.com/settings/developers
GITHUB_CLIENT_ID=Ov23liMZ79eOs4RrHY9n
GITHUB_CLIENT_SECRET=bf2d9a7261e0a1df571ab88413876c4ffa54499d
GITHUB_WEBHOOK_SECRET=75e8a9903dbfaa25d370ed4b905260ad96cacbc86f588a9052027342e80b93f9

# Security Keys - Generate these (min 32 chars)
SECRET_KEY=725d93df2aa92dbdfcfa5a178754d65b04f439b03790a5b097f4e722b424f5c5
JWT_SECRET=0d002005f8a70cb6f4472283ecfb23698d9fb14f7043ec4a1b06dcf96ff6b428

# LLM Provider - At least ONE required
OPENAI_API_KEY=sk-...
# OR
ANTHROPIC_API_KEY=sk-ant-...
# OR  
GEMINI_API_KEY=AIza...
GEMINI_MODEL_NAME=gemini-2.0-flash

# Settings
ENVIRONMENT=production
PORT=8000
CHAT_ENABLE_RAG=True

# Optional Admin Bootstrap
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_EMAIL=admin@company.com
```

### 3. Deploy
```bash
git push origin main
# OR click "Deploy" in Railway dashboard
# Railway auto-rebuilds
```

### 4. Get Production URL
In Railway dashboard → [Service] → Deployments → Copy the Railway domain
- Format: `https://[service-name]-[hash].railway.app`
- Update `VITE_API_BASE_URL` in Vercel to this URL
- Redeploy Vercel

### 5. Verify Backend
```bash
curl https://api.prguard.railway.app/health
# Expected: 200 OK
```

---

## Render (Alternative to Railway)

### 1. Create Service
1. Go to render.com → New+ → Web Service
2. Connect GitHub repo
3. Configure:
   - **Environment:** Python 3.11
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python backend/run.py`
   - **Instance Type:** Free or Starter

### 2. Environment Variables
Go to **Environment → Environment Variables**

Paste all variables from Railway section above.

### 3. Deploy
Save → Render auto-deploys

### 4. Get Production URL
In Render dashboard → [Your Service] → Domains
- Copy the `.onrender.com` URL
- Update `VITE_API_BASE_URL` in Vercel

---

## GitHub OAuth Setup

### 1. Get OAuth Credentials
1. Go to GitHub.com → Settings → Developer settings → OAuth Apps
2. Create New OAuth App:
   - **Application Name:** PRGuard
   - **Homepage URL:** `https://prguard.vercel.app`
   - **Authorization callback URL:** `https://api.prguard.railway.app/auth/github/callback`
3. Copy:
   - **Client ID** → `GITHUB_CLIENT_ID`
   - **Client Secret** → `GITHUB_CLIENT_SECRET`

### 2. Set on Backend
Add to Railway/Render environment:
```bash
GITHUB_CLIENT_ID=Ov23...
GITHUB_CLIENT_SECRET=bf2d...
```

### 3. Generate Webhook Secret
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Output: 75e8a9903dbfaa25d370ed4b905260ad96cacbc86f588a9052027342e80b93f9
```

Add to backend:
```bash
GITHUB_WEBHOOK_SECRET=75e8...
```

---

## Database Setup (Supabase/PostgreSQL)

### 1. Create PostgreSQL Database
- **Supabase:** Go to supabase.com → New Project → PostgreSQL
- **OR Railway:** PostgreSQL plugin
- **OR Render:** PostgreSQL service

### 2. Get Connection String
Format: `postgresql://user:password@host:port/dbname?sslmode=require`

Example:
```bash
postgresql://postgres:pass123@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require
```

### 3. Add to Backend
```bash
DATABASE_URL=postgresql://...
```

### 4. Run Migrations
```bash
# Migrations run automatically on backend startup
# Check backend logs for: "[STARTUP] Database initialized"
```

---

## Testing Post-Deployment

### Test 1: Frontend Loads
```bash
curl https://prguard.vercel.app
# Should return HTML
```

### Test 2: Backend Responds
```bash
curl https://api.prguard.railway.app/health
# Should return 200 OK with health status
```

### Test 3: CORS Configured
```bash
curl -X OPTIONS \
  -H "Origin: https://prguard.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  https://api.prguard.railway.app/api/chat -v
  
# Look for:
# < access-control-allow-origin: https://prguard.vercel.app
# < access-control-allow-credentials: true
```

### Test 4: Auth Flow
1. Open `https://prguard.vercel.app`
2. Click "Login with GitHub"
3. Authorize the app
4. Should redirect back to `/dashboard`
5. In browser DevTools → Application → Cookies
   - Should see `prguard_session` with `Secure` + `HttpOnly` flags

### Test 5: API Key Save
1. Go to Settings → LLM Provider
2. Enter test API key (e.g., `sk-ant-test123`)
3. Click Save
4. DevTools → Network tab → Watch requests:
   - `PUT /api/api-keys/claude` → Should return 200
   - `GET /api/api-keys` → Should have `has_any_key: true`
5. Verify UI shows green dot (connected)

### Test 6: Chat Works
1. Select repository from sidebar
2. Type message in chat input
3. Send message
4. DevTools → Network → Should see:
   - `POST /api/chat` → 200 (streams response)
5. Response should appear in chat

### Test 7: Session Persists
1. Save API key
2. Refresh page (F5)
3. Verify:
   - Still logged in (no GitHub login required)
   - API key still shows as connected
   - localStorage still has `prguard_session`

---

## Environment Variable References

### Production URLs Must Match These Format

| Service | URL Format | Example |
|---------|-----------|---------|
| Frontend | HTTPS only | `https://prguard.vercel.app` |
| Backend | HTTPS only | `https://api.prguard.railway.app` |
| Database | PostgreSQL with SSL | `postgresql://...?sslmode=require` |

### API Key Formats

| Provider | Format | Example |
|----------|--------|---------|
| Claude | Starts with `sk-ant-` | `sk-ant-...` |
| OpenAI | Starts with `sk-` | `sk-...` |
| Gemini | Starts with `AIza` | `AIza...` |

### Security Key Generation

```bash
# Generate SECRET_KEY and JWT_SECRET (min 32 chars)
python -c "import secrets; print(secrets.token_hex(32))"

# Example output:
# 725d93df2aa92dbdfcfa5a178754d65b04f439b03790a5b097f4e722b424f5c5
```

---

## Troubleshooting Production Issues

### Issue: Frontend shows "Cannot reach API"
**Check:**
1. Backend is running: `curl https://api.prguard.railway.app/health`
2. `VITE_API_BASE_URL` is set correctly in Vercel
3. Frontend was redeployed after setting env var
4. CORS headers present: See "Test 3" above

**Fix:**
```bash
# In Vercel dashboard:
# 1. Go to Settings → Environment Variables
# 2. Verify VITE_API_BASE_URL value
# 3. Go to Deployments → Click latest → Redeploy
```

### Issue: "401 Unauthorized" on API calls
**Check:**
1. User is logged in (check `localStorage: prguard_session`)
2. Session token is valid
3. Backend session middleware is working

**Fix:**
```bash
# Clear localStorage and log in again
# In browser console:
localStorage.clear()
# Then refresh and log in via GitHub
```

### Issue: Connected dots stay grey after saving API key
**Check:**
1. Response has `has_any_key: true`: DevTools → Network → Response tab
2. Request returns 200: Status code check
3. Session is valid: Check for 401 errors

**Fix:**
```bash
# In browser console:
const status = await (await fetch('https://api.prguard.railway.app/api/api-keys', 
  { headers: { 'X-Session-Token': JSON.parse(localStorage.getItem('prguard_session')).token } }
)).json()
console.log(status)
# Should show has_any_key: true
```

### Issue: "Chatting about null" message
**Check:**
1. Repos are loading: `GET /api/repos` returns items
2. User can click repo to select it
3. `selectedRepo` becomes non-null

**Fix:**
- Select a repository from the sidebar first
- Chat should show "Chatting about [repo-name]"
- If repos don't load, check user is authenticated

### Issue: Cookies not being sent
**Check:**
1. Both frontend and backend are HTTPS
2. `prguard_session` cookie has `Secure` flag (DevTools → Cookies)
3. CORS has `allow_credentials: true`

**Verify in backend logs:**
```bash
# Should see:
# "[Middleware] Session cookie received"
# OR "[Middleware] X-Session-Token header received"
```

---

## Monitoring Production

### View Backend Logs
- **Railway:** Dashboard → [Service] → Logs
- **Render:** Dashboard → [Service] → Logs

**Look for:**
```
[STARTUP] Starting PRGuard backend...
[STARTUP] Environment validation complete.
[STARTUP] Initializing database...
[STARTUP] Database initialized.
runtime_route GET /api/repos
runtime_route PUT /api/api-keys/{provider}
```

### View Frontend Errors
1. Open browser DevTools → Console
2. Look for CORS, 401, or network errors
3. Check Network tab for failed requests

### Database Connection Test
```bash
# In backend container/logs:
# Should see successful connection attempts
# Should NOT see:
# - "Connection refused"
# - "FATAL: database does not exist"
# - "FATAL: role does not exist"
```

---

## Rollback Procedure

### If Production Breaks

#### Vercel Rollback
1. Dashboard → Deployments
2. Find last working deployment
3. Click → Redeploy

#### Railway Rollback
1. Dashboard → [Service] → Deployments
2. Find last working deployment
3. Click → Rollback

#### Keep Old `.env` Backed Up
```bash
# Backup before changes
cp backend/.env backend/.env.backup-2024-01-15

# Can restore if needed
cp backend/.env.backup-2024-01-15 backend/.env
```

---

## Production Checklist (Before Going Live)

- [ ] **Frontend**
  - [ ] GitHub repo connected to Vercel
  - [ ] `VITE_API_BASE_URL` set in Vercel environment
  - [ ] Latest commit deployed and built
  - [ ] `npm run build` runs without errors locally

- [ ] **Backend**
  - [ ] GitHub repo connected to Railway/Render
  - [ ] ALL environment variables set (see Railway section)
  - [ ] Database migrations completed (check logs)
  - [ ] `/health` endpoint returns 200

- [ ] **GitHub OAuth**
  - [ ] OAuth app created at github.com/settings/developers
  - [ ] Credentials set in backend env vars
  - [ ] Callback URL matches backend domain

- [ ] **CORS & SSL**
  - [ ] Frontend is HTTPS only
  - [ ] Backend is HTTPS only
  - [ ] CORS test passes (headers returned)
  - [ ] Cookies have `Secure` flag

- [ ] **Functional Tests**
  - [ ] Can log in via GitHub
  - [ ] Can save API key (shows green dot)
  - [ ] Can select repository
  - [ ] Can chat with selected repo
  - [ ] Session persists after refresh

- [ ] **Monitoring**
  - [ ] Backend logs accessible
  - [ ] Frontend console clean (no errors)
  - [ ] Database connections stable

