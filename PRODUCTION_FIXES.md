# PRGuard Production Fixes

## Files to Update

### 1. frontend/.env.production (NEW FILE)
```bash
# Frontend build-time environment
VITE_API_BASE_URL=https://api.prguard.railway.app
VITE_API_PROXY_TARGET=
NODE_ENV=production
```

---

### 2. frontend/src/api/client.js - CURRENT CODE IS CORRECT ✅

The client already:
- ✅ Reads `VITE_API_BASE_URL` from env
- ✅ Falls back to Vite proxy in dev
- ✅ Has `withCredentials: true` for cross-origin cookies
- ✅ Sends `X-Session-Token` header as fallback

**Verify production build:**
```bash
cd frontend
VITE_API_BASE_URL=https://api.prguard.railway.app npm run build
# Build will bake the URL into dist files
```

---

### 3. frontend/src/components/ChatPanel.jsx - FIX

**Current code has issue:**
```javascript
export default function ChatPanel({ selectedRepo, selectedIssue, ... }) {
  // If selectedRepo is null, renders "Chatting about null"
  return (
    ...
    <div>{selectedIssue ? `Issue #${...}` : `Chatting about ${selectedRepo}`}</div>
  )
}
```

**FIXED CODE:**
Replace the ChatPanel export with:

```javascript
export default function ChatPanel({ selectedRepo, selectedIssue, ... }) {
  const { theme } = useContext(ThemeContext)
  const t = getTheme(theme)
  const dark = theme === 'dark'
  
  // If no repo selected, show connect modal instead of chat
  if (!selectedRepo) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', overflow: 'hidden, minWidth: 0 }}>
        <ConnectRepoModal dark={dark} />
      </div>
    )
  }
  
  // ... rest of ChatPanel code
}
```

---

### 4. backend/app/config.py - VERIFY CORS ✅

**Current implementation is CORRECT:**

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

**Requirements for production:**
- ✅ Set `FRONTEND_URL=https://prguard.vercel.app` on backend
- ✅ Backend will automatically whitelist this origin

---

### 5. backend/app/main.py - CORS MIDDLEWARE ✅

**Current implementation is CORRECT:**

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

---

### 6. backend/app/routes/auth.py - COOKIE SETTINGS ✅

**VERIFY this is being set correctly:**

```python
# After JWT creation in OAuth callback:
response = RedirectResponse(url=f"{settings.FRONTEND_URL}/callback?token={token}")
response.set_cookie(
    key="prguard_session",
    value=token,
    max_age=86400 * 7,           # 7 days
    secure=True,                 # 🔒 HTTPS only (production requirement)
    httponly=True,               # 🔒 No JS access
    samesite="None",             # 🔒 Cross-origin
)
return response
```

**For production:**
- ✅ Backend must be HTTPS (Railway provides this)
- ✅ Frontend must be HTTPS (Vercel provides this)
- ✅ Cookie will only be sent over HTTPS

---

### 7. frontend/src/pages/Dashboard.jsx - API KEY FLOW ✅

**Current implementation is CORRECT:**

The dashboard already:
- ✅ Calls `refreshApiStatus()` immediately after save
- ✅ Waits 800ms before second refresh (handles async backend)
- ✅ Fires `prguard:api-keys-updated` event
- ✅ Event updates status bar + model picker

**No changes needed.**

---

### 8. frontend/src/hooks/useApiKeyGuard.js - API KEY POLLING ✅

**Current implementation is CORRECT:**

```javascript
export const useApiKeyGuard = () => {
  const [hasKey, setHasKey] = useState(false)
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    let mounted = true
    const checkKey = async () => {
      try {
        const status = await getApiKeyStatus()
        if (mounted) {
          setHasKey(Boolean(status?.has_any_key))
        }
      } catch (err) {
        console.warn('[useApiKeyGuard] Failed to check API key status:', err)
        if (loading && mounted) {
          setHasKey(false)
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }
    
    checkKey()
    
    // Poll every 8s + listen for updates
    const interval = setInterval(checkKey, 8000)
    window.addEventListener('prguard:api-keys-updated', checkKey)
    
    return () => {
      mounted = false
      clearInterval(interval)
      window.removeEventListener('prguard:api-keys-updated', checkKey)
    }
  }, [])
  
  return { hasKey, loading }
}
```

---

### 9. backend/app/services/user_api_keys.py - RESPONSE SHAPE ✅

**VERIFY `list_user_key_statuses()` returns:**

```python
async def list_user_key_statuses(db: AsyncSession, *, user_id: str) -> dict:
    rows = await get_user_key_rows(db, user_id)
    items = []
    active_provider = None
    
    for row in rows:
        try:
            decrypted = decrypt_secret(row.encrypted_api_key)
            has_key = bool(decrypted)
            masked = mask_key(decrypted)
        except Exception as e:
            decrypted = ""
            has_key = False
            masked = "corrupt/invalid"
        
        if row.is_active:
            active_provider = row.provider
        
        items.append({
            "provider": row.provider,
            "has_key": has_key,
            "masked_key": masked,
            "is_active": bool(row.is_active),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })
    
    return {
        "items": sorted(items, key=lambda item: item["provider"]),
        "active_provider": active_provider,
        "has_any_key": any(item["has_key"] for item in items),  # 🔒 CRITICAL
    }
```

**🔒 CRITICAL:** Must include `has_any_key` field!

---

### 10. Render/Railway Backend Deployment

**Environment variables to set:**

```bash
# Database
DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require

# URLs (CRITICAL for CORS + OAuth)
FRONTEND_URL=https://prguard.vercel.app
APP_URL=https://api.prguard.railway.app

# GitHub OAuth
GITHUB_CLIENT_ID=Ov23liMZ79eOs4RrHY9n
GITHUB_CLIENT_SECRET=bf2d9a7261e0a1df571ab88413876c4ffa54499d
GITHUB_WEBHOOK_SECRET=75e8a9903dbfaa25d370ed4b905260ad96cacbc86f588a9052027342e80b93f9

# Security Keys (generate new ones)
SECRET_KEY=725d93df2aa92dbdfcfa5a178754d65b04f439b03790a5b097f4e722b424f5c5
JWT_SECRET=0d002005f8a70cb6f4472283ecfb23698d9fb14f7043ec4a1b06dcf96ff6b428

# At least ONE LLM provider required
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

# Optional admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure_password
ADMIN_EMAIL=admin@company.com
```

---

### 11. Vercel Frontend Deployment

**Environment variables to set:**

1. Go to Vercel dashboard → Project Settings → Environment Variables
2. Add:
   ```
   Name: VITE_API_BASE_URL
   Value: https://api.prguard.railway.app
   Environments: Production, Preview, Development
   ```
3. Go to Deployments → Redeploy latest commit (to rebuild with new env var)

**Verify build step:**
```bash
npm run build
# This will embed VITE_API_BASE_URL into the dist files
```

---

## Production Deployment Steps

### Step 1: Update Frontend
```bash
cd frontend

# Create .env.production
cat > .env.production << EOF
VITE_API_BASE_URL=https://api.prguard.railway.app
NODE_ENV=production
EOF

# Test build locally
npm run build

# Push to git
git add .env.production
git commit -m "Add production environment"
git push
```

### Step 2: Set Vercel Environment Variables
```bash
# In Vercel dashboard:
# Settings → Environment Variables
# VITE_API_BASE_URL = https://api.prguard.railway.app
# Redeploy
```

### Step 3: Set Railway/Render Backend Environment Variables
```bash
# In Railway/Render dashboard:
# Add all variables from section 10 above
```

### Step 4: Test Production Environment

#### 4a. Test Backend Health
```bash
curl https://api.prguard.railway.app/health
# Should return 200 OK
```

#### 4b. Test CORS Headers
```bash
curl -X OPTIONS \
  -H "Origin: https://prguard.vercel.app" \
  -H "Access-Control-Request-Method: GET" \
  https://api.prguard.railway.app/api/api-keys -v

# Look for:
# access-control-allow-origin: https://prguard.vercel.app
# access-control-allow-credentials: true
```

#### 4c. Test Frontend API Calls
1. Open browser DevTools → Network tab
2. Go to https://prguard.vercel.app
3. Check network requests:
   - Should hit `https://api.prguard.railway.app/...`
   - NOT `localhost:8000`

#### 4d. Test Auth Flow
1. Click "Login with GitHub"
2. Verify redirect back to https://prguard.vercel.app/callback
3. Check browser cookies: should have `prguard_session` with Secure + HttpOnly

#### 4e. Test API Key Save
1. Go to Settings
2. Save test API key
3. Watch Network tab:
   - `PUT /api/api-keys/claude` → 200
   - Response has `is_active: true`
4. Verify UI shows green dot

#### 4f. Test Chat
1. Select repository
2. Type message
3. Verify it sends to backend
4. Check for streamed response

---

## Troubleshooting Commands

### Check what VITE_API_BASE_URL was baked into build:
```bash
# In browser console after page loads:
console.log(JSON.parse(document.querySelector('[type="application/json"]')?.textContent || '{}').viteConfig?.base)
```

### Check frontend is calling correct API URL:
```bash
# In DevTools Network tab:
# Click any /api/ request → Headers tab
# Look for "Request URL" — should be https://api.prguard.railway.app/...
```

### Check backend is allowing CORS:
```bash
# In DevTools Network tab:
# Click any /api/ request → Response Headers tab
# Look for "access-control-allow-origin: https://prguard.vercel.app"
```

### Check session token is being sent:
```bash
# In DevTools Network tab:
# Click any /api/ request → Request Headers tab
# Look for "x-session-token: ..." OR "cookie: prguard_session=..."
```

---

## Final Checklist

- [ ] Backend `.env` has `FRONTEND_URL=https://prguard.vercel.app`
- [ ] Backend `.env` has `APP_URL=https://api.prguard.railway.app`
- [ ] Backend `.env` has at least one LLM API key
- [ ] Backend `.env` has `SECRET_KEY` and `JWT_SECRET` (min 32 chars)
- [ ] Frontend `.env.production` has `VITE_API_BASE_URL=https://api.prguard.railway.app`
- [ ] Frontend rebuilt with `npm run build` after setting env var
- [ ] Frontend deployed to Vercel
- [ ] Backend deployed to Railway/Render
- [ ] CORS test passes (header returned)
- [ ] Auth flow test passes (can log in)
- [ ] API key save test passes (green dot shows)
- [ ] Chat works (can select repo + send message)
- [ ] Session persists (refresh page, still logged in)

