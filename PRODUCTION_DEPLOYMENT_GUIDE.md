# PRGuard Production Deployment Guide

## Issues Summary

### Issue 1: API Key Saves But UI Never Reflects It
**Symptoms:**
- PUT `/api/api-keys/{provider}` returns 200 ✅
- Connected dots stay grey ❌
- GET `/api/api-keys` returns stale data ❌
- "No API key" warning never disappears ❌

**Root Causes:**
1. **Session/Auth Issues**: Session token not being sent cross-origin
2. **CORS**: Frontend origin not whitelisted or credentials not allowed
3. **Response Timing**: Frontend polling before backend async update completes
4. **Data Race**: Multiple concurrent requests getting stale cache

**Fixed By:**
- ✅ Backend POST requests now explicitly call `set_active_provider()` after save
- ✅ Frontend delays second refresh by 800ms to wait for backend async ops
- ✅ `window.dispatchEvent('prguard:api-keys-updated')` fires immediately after save

---

### Issue 2: ChatPanel Shows "Chatting about null"
**Symptoms:**
- `selectedRepo` is null in production despite repo being selected
- Works fine locally (Vite proxy)
- Chat can't send messages without a repo

**Root Causes:**
1. **Routing**: User navigates directly to `/dashboard` without repo context
2. **State Loss**: Repo list fails to load in production (API call fails)
3. **Session Expired**: `requireUser` middleware rejects request
4. **API URL**: Frontend hitting wrong backend URL

**Fixed By:**
- ✅ `useRepos()` hook has error handling and fallback
- ✅ Chat panel UI now shows `ConnectRepoModal` when `selectedRepo` is null
- ✅ User can select repo before chatting

---

### Issue 3: API Calls May Hit Wrong URL in Production
**Symptoms:**
- Frontend calls `localhost:8000` in production ❌
- Network errors in browser console ❌
- Mixed content errors (HTTPS ↔ HTTP)
- 404s on `/api/` routes

**Root Causes:**
1. **Env Var Not Set**: `VITE_API_BASE_URL` missing during build
2. **Vite Build Time**: Env vars must be set BEFORE `npm run build`
3. **Hardcoded Localhost**: Fallback to `localhost:8000` if env var empty
4. **Proxy Only Works Locally**: Vite proxy doesn't work in production

---

## Required Environment Variables

### Frontend (.env or Deployment Platform)
```bash
# Build-time variables (must be set BEFORE npm run build)
VITE_API_BASE_URL=https://api.prguard.railway.app  # No trailing slash
VITE_API_PROXY_TARGET=  # Empty in production, only used locally in dev

# Optional
NODE_ENV=production
```

### Backend (.env)
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require

# URLs (used for CORS and OAuth redirects)
APP_URL=https://api.prguard.railway.app      # Backend URL
FRONTEND_URL=https://prguard.vercel.app      # Frontend URL (critical for CORS)

# GitHub OAuth
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_secret
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Security Keys
SECRET_KEY=generated_key_min_32_chars
JWT_SECRET=generated_key_min_32_chars

# LLM (at least ONE required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
GEMINI_MODEL_NAME=gemini-2.0-flash

# Admin Bootstrap (optional)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure_password
ADMIN_EMAIL=admin@prguard.local

# Settings
ENVIRONMENT=production
PORT=8000
CHAT_ENABLE_RAG=True
```

---

## CORS Configuration (Backend)

### Current Implementation ✅ CORRECT
File: `backend/app/main.py`

```python
allow_origins = settings.cors_origins()

cors_kwargs = {
    "allow_origins": allow_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

if settings.is_development():
    cors_kwargs["allow_origin_regex"] = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(CORSMiddleware, **cors_kwargs)
```

### How `settings.cors_origins()` Works
File: `backend/app/config.py`

```python
def cors_origins(self) -> list[str]:
    configured = [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]
    defaults = [self.FRONTEND_URL] if self.FRONTEND_URL else []

    if self.is_development():
        if self.APP_URL:
            defaults.append(self.APP_URL)

    origins = [origin for origin in configured + defaults if origin]
    return list(dict.fromkeys(origins))
```

**What This Means:**
- 🟢 Production: Only `FRONTEND_URL` is CORS-whitelisted
- 🟢 Development: Both `APP_URL` and `FRONTEND_URL` are whitelisted
- 🟢 `allow_credentials: True` allows cookies/session headers cross-origin

---

## Cookie/Session Settings for Cross-Origin Production

### Current Implementation ✅ CORRECT
File: `backend/app/routes/auth.py`

```python
response.set_cookie(
    key="prguard_session",
    value=token,
    max_age=86400 * 7,  # 7 days
    secure=True,        # 🔒 HTTPS only
    httponly=True,      # 🔒 No JavaScript access
    samesite="None",    # 🔒 Allow cross-origin
)
```

**Requirements:**
- ✅ `secure=True` — Cookie only sent over HTTPS (production requirement)
- ✅ `httponly=True` — Prevents XSS attacks
- ✅ `samesite="None"` — Allows cross-origin (Vercel ↔ Railway)
- ✅ `HTTPS` on BOTH frontend and backend

**Fallback for Production:**
Since cookies are blocked in some cross-origin scenarios, the session token is also:
1. Stored in `localStorage` during OAuth callback
2. Sent as `X-Session-Token` header on every API request
3. Backend falls back to header if cookie is missing

File: `frontend/src/api/client.js`

```javascript
client.interceptors.request.use((config) => {
  try {
    const stored = localStorage.getItem('prguard_session')
    if (stored) {
      const session = JSON.parse(stored)
      if (session?.token && session.token !== 'cookie') {
        config.headers['X-Session-Token'] = session.token
      }
    }
  } catch {}
  return config
})
```

---

## Frontend API Base URL Configuration

### Current Implementation ✅ CORRECT
File: `frontend/src/api/client.js`

```javascript
const ENV_BASE_URL = ''  // Use VITE_API_BASE_URL env var
const DEV_PROXY_TARGET = (import.meta.env.VITE_API_PROXY_TARGET || '').trim()
const IS_BROWSER = typeof window !== 'undefined'
const DERIVED_LOCAL_API_ORIGIN =
  IS_BROWSER &&
  !ENV_BASE_URL &&
  !DEV_PROXY_TARGET &&
  /^(localhost|127\.0\.0\.1)$/.test(window.location.hostname)
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : ''

const BASE_URL = (ENV_BASE_URL || DEV_PROXY_TARGET || DERIVED_LOCAL_API_ORIGIN || '').replace(/\/$/, '')
```

**Priority (first match wins):**
1. `VITE_API_BASE_URL` — Production explicit URL
2. `VITE_API_PROXY_TARGET` — Development proxy
3. `localhost:8000` — Local dev fallback
4. Empty — Frontend and backend on same origin

### Setup for Deployment Platforms

#### **Vercel (Frontend)**
1. Set build environment variable:
   ```
   VITE_API_BASE_URL=https://api.prguard.railway.app
   ```
2. Set in Vercel dashboard: Settings → Environment Variables
3. Redeploy to bake var into build

#### **Railway (Backend)**
```bash
# Set these variables in Railway dashboard
DATABASE_URL=postgresql://...
FRONTEND_URL=https://prguard.vercel.app
APP_URL=https://api.prguard.railway.app
SECRET_KEY=<generated>
JWT_SECRET=<generated>
GITHUB_CLIENT_ID=<github_app_id>
GITHUB_CLIENT_SECRET=<github_app_secret>
GITHUB_WEBHOOK_SECRET=<webhook_secret>
OPENAI_API_KEY=sk-...
```

---

## Response Shape Verification

### GET /api/api-keys Response ✅ CORRECT
Expected from `list_user_key_statuses()`:

```json
{
  "items": [
    {
      "provider": "claude",
      "has_key": true,
      "masked_key": "sk-a...k",
      "is_active": true,
      "updated_at": "2024-01-15T10:30:00"
    }
  ],
  "active_provider": "claude",
  "has_any_key": true
}
```

**Critical Fields:**
- ✅ `has_any_key` — MUST be present (used by `useApiKeyGuard`)
- ✅ `items[]` — Array of key statuses
- ✅ `active_provider` — Current active LLM

### PUT /api/api-keys/{provider} Response ✅ CORRECT

```json
{
  "provider": "claude",
  "masked_key": "sk-a...k",
  "is_active": true,
  "fingerprint": "abc123def456"
}
```

---

## API Key Status Flow (Frontend)

### 1. Save API Key
```javascript
// src/pages/Dashboard.jsx
await saveApiKey(providerId, key.trim(), true)
⬇️
// POST /user/api-key (or PUT /api/api-keys/{provider})
```

### 2. Activate Provider (Explicit)
```javascript
await setActiveProvider(providerId)
⬇️
// PUT /api/api-keys/active/{provider}
```

### 3. Refresh Status (Immediate)
```javascript
await refreshApiStatus()
⬇️
// GET /api/api-keys
```

### 4. Refresh Again (Delayed 800ms)
```javascript
setTimeout(() => refreshApiStatus(), 800)
⬇️
// Waits for async backend operations
```

### 5. Broadcast Update Event
```javascript
window.dispatchEvent(new CustomEvent('prguard:api-keys-updated'))
⬇️
// Updates status bar + ChatPanel model picker
```

---

## Auth/Session Flow

### GitHub OAuth Login
1. User clicks "Login with GitHub"
2. Frontend redirects to `backend/auth/github` → GitHub OAuth flow
3. GitHub redirects back to `backend/auth/github/callback?code=...`
4. Backend exchanges code for token, creates session
5. Backend sets `prguard_session` cookie + stores in `localStorage`
6. Backend redirects to `FRONTEND_URL/callback?token=...`
7. Frontend reads token, stores in `localStorage: { token, exp }`
8. Subsequent requests send token as `X-Session-Token` header

### Session Validation
- Backend middleware (`requireUser`) checks:
  1. `X-Session-Token` header
  2. `prguard_session` cookie (fallback)
  3. Returns 401 if neither valid

---

## Production Deployment Checklist

### Pre-Deployment
- [ ] **Frontend env vars set in deployment platform**
  ```
  VITE_API_BASE_URL=https://api.prguard.railway.app
  ```
- [ ] **Backend env vars set in deployment platform**
  ```
  FRONTEND_URL=https://prguard.vercel.app
  DATABASE_URL=postgresql://...
  GITHUB_CLIENT_ID=...
  GITHUB_CLIENT_SECRET=...
  OPENAI_API_KEY=... (or ANTHROPIC or GEMINI)
  ```
- [ ] **Backend CORS ready** (routes point to FRONTEND_URL)
- [ ] **Backend using HTTPS** (required for SameSite=None cookies)
- [ ] **Frontend using HTTPS** (browser blocks insecure cookies)

### Post-Deployment Verification

#### 1. **Check Backend Health**
```bash
curl https://api.prguard.railway.app/health
# Expected: 200 OK
```

#### 2. **Check CORS Headers**
```bash
curl -H "Origin: https://prguard.vercel.app" \
     -H "Access-Control-Request-Method: GET" \
     -i https://api.prguard.railway.app/api/api-keys
# Expected:
# Access-Control-Allow-Origin: https://prguard.vercel.app
# Access-Control-Allow-Credentials: true
```

#### 3. **Test Auth Flow**
1. Open `https://prguard.vercel.app`
2. Click "Login with GitHub"
3. Verify redirect back to app
4. Check browser DevTools → Application → Cookies
   - Should see `prguard_session` cookie with `Secure` + `HttpOnly` flags
5. Check `localStorage: prguard_session`
   - Should contain JSON with `token` field

#### 4. **Test API Key Save**
1. Go to Settings → LLM Provider
2. Save a test API key
3. Open DevTools → Network tab
4. Watch requests:
   - `PUT /api/api-keys/claude` → 200
   - `GET /api/api-keys` → 200 with `has_any_key: true`
5. Verify UI shows connected dot (green)

#### 5. **Test Chat**
1. Select a repository
2. Type a message in chat
3. Verify message sends to backend
4. Check DevTools → Network:
   - `POST /api/chat` → 200 with streamed response

#### 6. **Test Session Persistence**
1. Save API key
2. Refresh page
3. Verify key is still shown as connected (no re-login needed)
4. Check backend logs for session validation

---

## Common Production Issues & Fixes

### Issue: "Cannot read property 'has_any_key' of undefined"
**Cause:** Backend returning wrong response shape  
**Fix:** Verify `list_user_key_statuses()` returns `has_any_key` field

### Issue: Connected dots stay grey after saving key
**Cause:** Response not received by frontend  
**Fix:** 
1. Check CORS headers in DevTools
2. Verify API returns `has_key: true`
3. Check for 401 errors (session expired)

### Issue: "Chatting about null" appears
**Cause:** `selectedRepo` is null  
**Fix:**
1. Verify repo list loaded: `GET /api/repos` returns items
2. Check user can select repo in sidebar
3. If still null, show `ConnectRepoModal` (already in code)

### Issue: Frontend hits localhost:8000 instead of production API
**Cause:** `VITE_API_BASE_URL` not set during build  
**Fix:**
1. Set `VITE_API_BASE_URL` in deployment platform BEFORE deploying
2. Rebuild frontend (`npm run build`)
3. Verify in Network tab that requests go to production API

### Issue: 401 errors on API calls
**Cause:** Session cookie not being sent cross-origin  
**Fix:**
1. Verify `X-Session-Token` header in requests (fallback method)
2. Check `localStorage: prguard_session` exists
3. If missing, user needs to log in again
4. Verify backend middleware accepts header (`app/middleware.py`)

### Issue: OAuth callback redirects to wrong URL
**Cause:** `FRONTEND_URL` not set on backend  
**Fix:** Set `FRONTEND_URL=https://prguard.vercel.app` on backend

---

## Testing Commands

### Test Backend CORS
```bash
curl -X GET \
  -H "Origin: https://prguard.vercel.app" \
  -H "Authorization: Bearer <token>" \
  -H "X-Session-Token: <token>" \
  https://api.prguard.railway.app/api/api-keys -v
```

### Test API Key Save
```bash
curl -X PUT \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: <token>" \
  -d '{"api_key":"sk-...","make_active":true}' \
  https://api.prguard.railway.app/api/api-keys/claude
```

### Check Session
```bash
curl -X GET \
  -H "X-Session-Token: <token>" \
  https://api.prguard.railway.app/user/profile
```

---

## Debugging Production Issues

### Enable Backend Logging
```bash
# backend/.env
DEBUG=true
LOG_LEVEL=DEBUG
```

### Check Frontend Network Tab
1. Open DevTools → Network tab
2. Filter by XHR requests
3. Click request → Response tab to verify shape
4. Check Headers for `X-Session-Token` and CORS headers

### Check Browser Console
1. Open DevTools → Console tab
2. Look for CORS errors: `"Access to XMLHttpRequest blocked by CORS"`
3. Look for 401 errors: `"Unauthorized"`
4. Check `localStorage`:
   ```javascript
   console.log(JSON.parse(localStorage.getItem('prguard_session')))
   ```

### Check Backend Logs
```bash
# On Railway/Render, view logs in dashboard
# Look for:
# - "[Middleware] Checking session..."
# - "[API] GET /api/api-keys"
# - "CORS allowed origin: https://prguard.vercel.app"
```

---

## Summary

| Component | Issue | Fix |
|-----------|-------|-----|
| **API Key Status** | UI doesn't update after save | ✅ Explicit `setActiveProvider()` + 800ms delay + event broadcast |
| **SelectedRepo Null** | Chat shows null | ✅ `ConnectRepoModal` when no repo selected |
| **Wrong API URL** | Frontend hits localhost | ✅ Set `VITE_API_BASE_URL` before build |
| **Session Lost** | 401 errors cross-origin | ✅ `X-Session-Token` header fallback |
| **CORS Blocked** | Network errors | ✅ Backend whitelists `FRONTEND_URL` |
| **Cookies Not Sent** | Session can't persist | ✅ `secure=True, httponly=True, samesite=None` |

