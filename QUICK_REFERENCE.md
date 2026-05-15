# Quick Reference: Commands & Testing

## Local Development Testing

### Start Backend Locally
```bash
cd backend

# Set env vars
export DATABASE_URL="postgresql://localhost/prguard"
export FRONTEND_URL="http://localhost:5173"
export APP_URL="http://localhost:8000"
export SECRET_KEY="dev-key-min-32-chars-xxxxxxxxxxxxxxxx"
export JWT_SECRET="dev-key-min-32-chars-xxxxxxxxxxxxxxxx"
export GITHUB_CLIENT_ID="your_github_client_id"
export GITHUB_CLIENT_SECRET="your_github_client_secret"

# Run
python run.py
# Server starts: http://localhost:8000
```

### Start Frontend Locally
```bash
cd frontend

# Install deps
npm install

# Set dev env vars (optional - proxy is default)
export VITE_API_PROXY_TARGET="http://localhost:8000"

# Run dev server
npm run dev
# Frontend: http://localhost:5173
# Vite proxy handles /api/* → localhost:8000
```

### Build Frontend for Production
```bash
cd frontend

# Build with production env vars
VITE_API_BASE_URL="https://api.prguard.railway.app" npm run build

# Output: dist/ folder ready for Vercel
# Verify build:
npm run preview
# Check: http://localhost:4173 — verify correct API URL is baked in
```

---

## API Testing (Production)

### Test 1: Health Check
```bash
curl https://api.prguard.railway.app/health
# Expected:
# 200 OK
# { "status": "ok" }
```

### Test 2: CORS Headers
```bash
curl -X OPTIONS \
  -H "Origin: https://prguard.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  https://api.prguard.railway.app/api/chat -v

# Look for in headers:
# access-control-allow-origin: https://prguard.vercel.app
# access-control-allow-credentials: true
# access-control-allow-methods: POST, GET, PUT, DELETE, OPTIONS
```

### Test 3: Authenticate (Get Session Token)
```bash
# Go to browser, log in via GitHub
# In DevTools Console:
JSON.parse(localStorage.getItem('prguard_session'))
# Copy the token value

# Example output:
# { token: "eyJhbGciOiJIUzI1NiIs...", exp: 1705334400 }

TOKEN="eyJhbGciOiJIUzI1NiIs..."
```

### Test 4: Get API Key Status
```bash
TOKEN="your_session_token"

curl -X GET \
  -H "X-Session-Token: $TOKEN" \
  https://api.prguard.railway.app/api/api-keys

# Expected:
# {
#   "items": [],
#   "active_provider": "claude",
#   "has_any_key": false
# }
```

### Test 5: Save API Key
```bash
TOKEN="your_session_token"
API_KEY="sk-..."  # Your real API key

curl -X PUT \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: $TOKEN" \
  -d '{"api_key":"'"$API_KEY"'","make_active":true}' \
  https://api.prguard.railway.app/api/api-keys/claude

# Expected:
# {
#   "provider": "claude",
#   "masked_key": "sk-a...e",
#   "is_active": true,
#   "fingerprint": "abc123..."
# }
```

### Test 6: Get Repositories
```bash
TOKEN="your_session_token"

curl -X GET \
  -H "X-Session-Token: $TOKEN" \
  https://api.prguard.railway.app/api/repos

# Expected:
# [
#   { "id": "123", "name": "my-repo", ... },
#   ...
# ]
```

### Test 7: Chat Message
```bash
TOKEN="your_session_token"

curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: $TOKEN" \
  -d '{
    "repo": "my-repo",
    "issue_number": null,
    "message": "How does auth work?"
  }' \
  https://api.prguard.railway.app/api/chat

# Expected:
# Streaming response with AI analysis
```

---

## Frontend Console Testing

### Check API URL
```javascript
// Run in DevTools Console on production site
const apiUrl = fetch('/api/health').url || 'unknown'
console.log('API URL:', apiUrl)
// Should show: https://api.prguard.railway.app/...
```

### Check Session Token
```javascript
const session = JSON.parse(localStorage.getItem('prguard_session'))
console.log('Session token:', session?.token)
console.log('Token expires:', new Date(session?.exp * 1000))
```

### Check API Key Status
```javascript
const resp = await fetch('/api/api-keys', {
  headers: { 'X-Session-Token': JSON.parse(localStorage.getItem('prguard_session')).token }
})
const status = await resp.json()
console.log('API Key Status:', status)
```

### Simulate API Key Update Event
```javascript
// Manually trigger UI update
window.dispatchEvent(new CustomEvent('prguard:api-keys-updated'))
// Status bar should update immediately
```

### Check Repos
```javascript
const resp = await fetch('/api/repos', {
  headers: { 'X-Session-Token': JSON.parse(localStorage.getItem('prguard_session')).token }
})
const repos = await resp.json()
console.log('Repos:', repos)
```

### Clear Session & Force Re-login
```javascript
localStorage.clear()
sessionStorage.clear()
// Refresh page — should redirect to login
```

---

## Debugging Network Requests

### Enable Detailed Logging

#### Frontend
```javascript
// In browser console before making requests:

// Log all API calls
const origFetch = window.fetch
window.fetch = async (...args) => {
  console.log('📤 Fetch:', args[0], args[1])
  const resp = await origFetch(...args)
  console.log('📥 Response:', resp.status, resp.statusText)
  return resp
}

// Now make API calls and watch console
```

#### Backend
```bash
# In backend .env or deployment:
DEBUG=true
LOG_LEVEL=DEBUG

# Backend will log:
# [Middleware] Processing request...
# [Auth] Checking session token...
# [API] GET /api/repos
```

### Monitor with DevTools Network Tab

1. Open DevTools → Network tab
2. Enable "Preserve log"
3. Make API call
4. Click request → Response tab to see JSON
5. Click request → Headers tab to see:
   - Request headers (X-Session-Token, Origin)
   - Response headers (CORS allow-origin, etc.)

---

## Error Messages & Fixes

### "Access to XMLHttpRequest blocked by CORS"
```
Fix:
1. Check Origin header in DevTools
2. Verify FRONTEND_URL set on backend
3. Check CORS headers returned: access-control-allow-origin
4. Restart backend after env change
```

### "401 Unauthorized"
```
Fix:
1. Check localStorage.getItem('prguard_session')
2. Log in again via GitHub
3. Check token hasn't expired
4. Verify X-Session-Token header is sent
```

### "Cannot read property 'has_any_key' of undefined"
```
Fix:
1. GET /api/api-keys returns wrong shape
2. Verify has_any_key field exists in response
3. Check list_user_key_statuses() in backend
```

### "Chatting about null"
```
Fix:
1. Verify repos loaded: GET /api/repos
2. Select repo from sidebar
3. Check useRepos() hook error handling
```

### "API calls go to localhost:8000 instead of production URL"
```
Fix:
1. Set VITE_API_BASE_URL in Vercel before build
2. Rebuild frontend: npm run build
3. Redeploy to Vercel
4. Verify new deploy baked URL into dist/
```

---

## Production Deployment Checklist

### Pre-Deployment (5 minutes before)

```bash
# 1. Verify backend vars are set
echo "FRONTEND_URL: $FRONTEND_URL"
echo "DATABASE_URL: ${DATABASE_URL:0:30}..."
echo "GITHUB_CLIENT_ID: $GITHUB_CLIENT_ID"

# 2. Test local backend
python backend/run.py &
sleep 2
curl http://localhost:8000/health

# 3. Test local frontend build
cd frontend
npm run build
npm run preview &
# Open http://localhost:4173 in browser
# Check Network tab — API calls go to $VITE_API_BASE_URL

# 4. Kill local servers
kill %1 %2
```

### Post-Deployment (5 minutes after)

```bash
# 1. Verify backend URL
curl https://api.prguard.railway.app/health
# Expected: 200 OK

# 2. Verify frontend loads
curl https://prguard.vercel.app
# Expected: 200, returns HTML

# 3. Check CORS
curl -X OPTIONS \
  -H "Origin: https://prguard.vercel.app" \
  https://api.prguard.railway.app/api/api-keys -v
# Expected: access-control-allow-origin header present

# 4. Manual testing:
# a. Open https://prguard.vercel.app
# b. Click Login → Log in via GitHub
# c. Go to Settings → Save test API key
# d. Verify green dot appears
# e. Select repo → Send chat message
# f. Refresh page → Verify session persists
```

---

## Performance Monitoring

### Response Times

```bash
# Test API response time
time curl https://api.prguard.railway.app/api/repos

# Expected: < 200ms
```

### Database Query Time

```bash
# In backend logs (Railway dashboard):
# Look for "[DB] Query took X ms"
# Should be < 100ms for most queries
```

### Frontend Build Size

```bash
cd frontend
npm run build

# Check dist size
du -sh dist/
# Should be < 500KB for gzipped assets
```

---

## Useful Commands Reference

### Database

```bash
# Connect to production database
psql "postgresql://user:pass@host:5432/dbname"

# List tables
\dt

# Check user table
SELECT id, username, email, role FROM "user" LIMIT 5;

# Check API keys
SELECT user_id, provider, is_active FROM user_api_key LIMIT 5;
```

### Docker (if using containers)

```bash
# Build image
docker build -t prguard:latest .

# Run container
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql://..." \
  -e FRONTEND_URL="https://prguard.vercel.app" \
  prguard:latest

# View logs
docker logs -f <container_id>
```

### Git Rollback

```bash
# View recent commits
git log --oneline -10

# Rollback to previous commit
git revert <commit_hash>
git push

# This will trigger auto-redeploy on Vercel/Railway
```

---

## Environment Variable Validation

```bash
# Check all required vars are set on backend:
python -c "
from app.config import settings
print('✅ FRONTEND_URL:', settings.FRONTEND_URL)
print('✅ APP_URL:', settings.APP_URL)
print('✅ DATABASE_URL:', settings.DATABASE_URL[:50] + '...')
print('✅ GITHUB_CLIENT_ID:', settings.GITHUB_CLIENT_ID)
print('✅ SECRET_KEY:', 'set' if settings.SECRET_KEY else 'MISSING')
print('✅ JWT_SECRET:', 'set' if settings.JWT_SECRET else 'MISSING')
print('✅ Has LLM:', any([settings.OPENAI_API_KEY, settings.ANTHROPIC_API_KEY, settings.GEMINI_API_KEY]))
"
```

