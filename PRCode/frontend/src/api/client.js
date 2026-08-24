import axios from 'axios'

const ENV_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()
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

const client = axios.create({
  baseURL:         BASE_URL,
  headers:         { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout:         60000,
})

// Raw client without interceptors for health-checking session state
const rawClient = axios.create({ baseURL: BASE_URL, withCredentials: true, timeout: 15000 })

let providerCache = 'claude'
let storedApiKey = ''

const normalizeProvider = (provider) => {
  const normalized = (provider || '').trim().toLowerCase()
  if (normalized === 'gpt4o') return 'gpt'
  return normalized || 'claude'
}

// Load API key from localStorage on module init
const initApiKey = () => {
  try {
    const stored = localStorage.getItem('prguard_api_key')
    if (stored) storedApiKey = stored
  } catch {}
}
initApiKey()

export const getScopedProvider = () => providerCache
export const setScopedProvider = (provider) => { providerCache = normalizeProvider(provider) }
export const getScopedApiKey = () => storedApiKey
export const setScopedApiKey = (key) => {
  storedApiKey = (key || '').trim()
  try {
    if (storedApiKey) {
      localStorage.setItem('prguard_api_key', storedApiKey)
    } else {
      localStorage.removeItem('prguard_api_key')
    }
  } catch {}
}
export const clearScopedApiKey = () => setScopedApiKey('')


export const normalizeApiKeyStatus = (payload = {}) => {
  const items = Array.isArray(payload.items) ? payload.items : []
  const active_provider = normalizeProvider(payload.active_provider || 'claude')
  const has_any_key = typeof payload.has_any_key === 'boolean'
    ? payload.has_any_key
    : items.some(item => Boolean(item?.has_key))

  return {
    ...payload,
    items,
    active_provider,
    has_any_key,
  }
}

// ── Request interceptor: attach session token and API key headers ────────────
// Session token is stored in localStorage and sent as X-Session-Token header.
// API key (if available) is sent as x-api-key header for LLM provider identification.
client.interceptors.request.use((config) => {
  try {
    const stored = localStorage.getItem('prguard_session')
    if (stored) {
      const session = JSON.parse(stored)
      if (session?.token && session.token !== 'cookie') {
        config.headers['X-Session-Token'] = session.token
        try {
          const debugEnabled = import.meta.env.DEV || import.meta.env.VITE_DEBUG_API === '1'
          if (debugEnabled && typeof console !== 'undefined' && console.debug) {
            console.debug('[API] Attaching X-Session-Token header', {
              url: config.url,
              method: config.method,
              tokenPreview: session.token ? `${session.token.slice(0, 6)}...` : null,
            })
          }
        } catch {}
      }

      const githubToken = session?.gh_token || session?.github_token
      if (githubToken) {
        config.headers['X-GitHub-Token'] = githubToken
      }
    }
  } catch {}

  // Attach API key header if available
  if (storedApiKey) {
    config.headers['x-api-key'] = storedApiKey
  }

  return config
})


// ── Global 401 handler ────────────────────────────────────────────────────────
// Validates session on 401 before expiring; distinguishes session vs API key errors.
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Log 401s in dev mode
    try {
      const debugEnabled = import.meta.env.DEV || import.meta.env.VITE_DEBUG_API === '1'
      if (debugEnabled && error?.response?.status === 401 && typeof console !== 'undefined' && console.error) {
        console.error('[API] 401 Unauthorized', {
          url: error.config?.url,
          method: error.config?.method,
          status: error.response?.status,
          response: error.response?.data,
        })
      }
    } catch {}

    if (error?.response?.status === 401) {
      // Only attempt to validate session if a localStorage session exists.
      const stored = (() => { try { return localStorage.getItem('prguard_session') } catch { return null } })()
      if (stored) {
        // Re-check server session via a raw client to avoid interceptor recursion.
        try {
          let tokenHeader = undefined
          try {
            const parsedStored = JSON.parse(stored)
            if (parsedStored?.token && parsedStored.token !== 'cookie') tokenHeader = parsedStored.token
          } catch {}
          const me = await rawClient.get('/auth/me', {
            validateStatus: (s) => s === 200 || s === 401,
            headers: tokenHeader ? { 'X-Session-Token': tokenHeader } : undefined,
          })
          if (me.status === 200 && me.data) {
            // Server still sees a valid session. Preserve any existing token in localStorage
            try {
              const parsedStored = JSON.parse(stored)
              const merged = { ...me.data }
              if (parsedStored?.token && !merged.token) merged.token = parsedStored.token
              if (parsedStored?.gh_token && !merged.gh_token) merged.gh_token = parsedStored.gh_token
              if (parsedStored?.github_token && !merged.github_token) merged.github_token = parsedStored.github_token
              localStorage.setItem('prguard_session', JSON.stringify(merged))
            } catch {}
            // Session is valid but this specific endpoint failed — likely API key or permissions issue
            // Do not dispatch auth:expired — let the specific handler deal with it
            error.isSessionValid = true
            return Promise.reject(error)
          }
        } catch (e) {
          // If the validation request failed, fall back to expiring the session below.
        }

        // Session is invalid — emit auth:expired
        window.dispatchEvent(new CustomEvent('auth:expired'))
      }
    }

    return Promise.reject(error)
  }
)


// ── Repos ─────────────────────────────────────────────────────────────────────
export const getRepos = async () => {
  try {
    const res = await client.get('/api/repos')
    return res.data
  } catch (err) {
    throw err
  }
}

export const getGithubRepos = async () => {
  try {
    const res = await client.get('/api/github/repos')
    return res.data
  } catch (err) {
    throw err
  }
}

export const connectRepo = async (repoId, repoName) => {
  try {
    const res = await client.post('/api/github/connect-repo', { repo_id: repoId, repo_name: repoName })
    return res.data
  } catch (err) {
    throw err
  }
}

export const disconnectRepo = async (repoId) => {
  try {
    const res = await client.delete(`/api/github/disconnect-repo?repo_id=${repoId}`)
    return res.data
  } catch (err) {
    throw err
  }
}


// ── Issues ────────────────────────────────────────────────────────────────────
export const getIssues = async (repo) => {
  try {
    const res = await client.get(`/api/issues?repo=${encodeURIComponent(repo)}`)
    return res.data
  } catch (err) {
    throw err
  }
}

export const toggleWorkingOn = async (issueNumber, repo, active) => {
  try {
    const res = await client.post(`/api/issues/${issueNumber}/working-on`, { repo, active })
    return res.data
  } catch (err) {
    throw err
  }
}


// ── Files ─────────────────────────────────────────────────────────────────────
export const getFiles = async (repo) => {
  try {
    const res = await client.get(`/api/files?repo=${encodeURIComponent(repo)}`)
    return res.data
  } catch (err) {
    throw err
  }
}

export const sendMessage = async (message, repo, issueNumber, history = [], options = {}) => {
  const provider = normalizeProvider(options.provider || getScopedProvider())
  try {
    console.log('[Chat API] Sending request', { repo, provider, historyLength: history.length })
    const res = await client.post('/api/chat', {
      message,
      repo,
      provider,
      issue_number: issueNumber || null,
      history: history.filter(m => !m.isError),
    }, { signal: options.signal })
    const payload = res.data || {}
    if (!payload.message && !payload.answer) throw new Error('Invalid chat response format from server.')
    const normalized = {
      ...payload,
      message: payload.message || payload.answer,
      answer: payload.answer || payload.message,
    }
    console.log('[Chat API] Response received', normalized)
    return normalized
  } catch (err) {
    console.error('[Chat API] Error:', err)
    if (err?.code === 'ERR_CANCELED') throw new Error('Request canceled by user.')
    const status = err?.response?.status
    const errorMsg = err?.response?.data?.detail || err?.message || 'Connection error. Check your settings.'
    if (status === 502) throw new Error('Backend server error (502). The application may be overloaded or restarting. Please try again in a moment.')
    else if (status === 500) throw new Error(`Server error: ${errorMsg}`)
    else if (status === 401) throw new Error('Session expired. Please sign in again.')
    else if (status === 403) throw new Error('Repository not connected. Connect the repository in Dashboard and retry.')
    else if (status === 400) throw new Error(`Invalid request: ${errorMsg}`)
    throw new Error(errorMsg)
  }
}

export const getApiKeyStatus = async () => {
  const res = await client.get('/api/api-keys')
  const payload = normalizeApiKeyStatus(res.data || {})
  providerCache = payload.active_provider
  return payload
}

export const getUserProfile = async () => {
  const res = await client.get('/user/profile')
  const payload = res.data || {}
  const status = normalizeApiKeyStatus(payload.api_key_status || {})
  providerCache = status.active_provider
  return { ...payload, api_key_status: status }
}

export const saveUserApiKey = async (provider, apiKey, makeActive = true) => {
  const normalized = normalizeProvider(provider)
  const res = await client.post('/user/api-key', { provider: normalized, api_key: apiKey, make_active: makeActive })
  if (makeActive) {
    providerCache = normalized
    setScopedApiKey(apiKey) // Persist to localStorage
  }
  return res.data
}

export const saveApiKey = async (provider, apiKey, makeActive = true) => {
  const normalized = normalizeProvider(provider)
  const res = await client.put(`/api/api-keys/${normalized}`, { api_key: apiKey, make_active: makeActive })
  if (makeActive) {
    providerCache = normalized
    setScopedApiKey(apiKey) // Persist to localStorage
  }
  return res.data
}

export const deleteApiKey = async (provider) => {
  const normalized = normalizeProvider(provider)
  const res = await client.delete(`/api/api-keys/${normalized}`)
  if (normalized === providerCache) {
    try { await getApiKeyStatus() } catch { providerCache = normalizeProvider('claude') }
  }
  return res.data
}

export const setActiveProvider = async (provider) => {
  const normalized = normalizeProvider(provider)
  const res = await client.put(`/api/api-keys/active/${normalized}`)
  providerCache = normalized
  return res.data
}


// ── Index repo ────────────────────────────────────────────────────────────────
export const indexRepo = async (repo) => {
  try {
    const res = await client.post('/api/index', { repo }, { timeout: 900000 })
    return res.data
  } catch (err) {
    throw err
  }
}

export const pollIndexJob = async (jobId) => {
  try {
    const res = await client.get(`/api/index/job/${jobId}`)
    return res.data
  } catch (err) {
    throw err
  }
}

export const getIndexStatus = async (repo) => {
  try {
    const res = await client.get(`/api/index/status?repo=${encodeURIComponent(repo)}`)
    return res.data
  } catch {
    return { indexed: false, chunks: 0 }
  }
}


// ── Auth ──────────────────────────────────────────────────────────────────────
export const getMe = async () => {
  try {
    const res = await client.get('/auth/me', {
      validateStatus: (status) => status === 200 || status === 401,
    })
    if (res.status === 401) return null
    return res.data
  } catch {
    return null
  }
}

export const logout = async () => {
  try {
    localStorage.removeItem('prguard_session')
    const res = await client.post('/auth/logout')
    return res.data || { redirect: '/login', role: 'user' }
  } catch {
    return { redirect: '/login', role: 'user' }
  }
}

export const adminLogin = async (identifier, password) => {
  const res = await client.post('/admin/login', { email: identifier, password })
  return res.data
}

export const getGithubLoginUrl = () => {
  const frontendOrigin = IS_BROWSER ? window.location.origin : ''
  const loginPath = `/auth/github?frontend_origin=${encodeURIComponent(frontendOrigin)}`
  return BASE_URL ? `${BASE_URL}${loginPath}` : loginPath
}

export const adminLogout = async () => {
  try {
    const res = await client.post('/admin/logout')
    return res.data || { redirect: '/', role: 'admin' }
  } catch {
    return { redirect: '/', role: 'admin' }
  }
}

export const getAdminMe = async () => {
  const res = await client.get('/admin/me', {
    validateStatus: (status) => status === 200 || status === 401 || status === 403,
  })
  if (res.status !== 200) return null
  return res.data
}

export const getAdminUsers = async (params = {}) => {
  const res = await client.get('/admin/users', { params })
  return res.data
}

export const getAdminUserById = async (id) => {
  const res = await client.get(`/admin/user/${id}`)
  return res.data
}

export const patchAdminUser = async (id, payload) => {
  const res = await client.patch(`/admin/user/${id}`, payload)
  return res.data
}

export const getAdminApiKeysStatus = async () => {
  const res = await client.get('/admin/api-keys-status')
  return res.data
}

export const getAdminLogs = async () => {
  const res = await client.get('/admin/logs')
  return res.data
}

export const getHealth = async () => {
  const res = await client.get('/health')
  return res.data
}

export default client
