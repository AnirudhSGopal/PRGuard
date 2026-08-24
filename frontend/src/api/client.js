import axios from 'axios'

const ENV_BASE_URL = import.meta.env.VITE_API_BASE_URL
const IS_BROWSER = typeof window !== 'undefined'
const IS_DEV = Boolean(import.meta.env.DEV)

if (typeof ENV_BASE_URL !== 'string' || !ENV_BASE_URL.trim()) {
  throw new Error('VITE_API_BASE_URL is required at runtime and cannot be empty.')
}

const BASE_URL = ENV_BASE_URL.trim().replace(/\/$/, '')
if (!IS_DEV && (BASE_URL.toLowerCase().includes('localhost') || BASE_URL.includes('127.0.0.1'))) {
  throw new Error('VITE_API_BASE_URL cannot point to localhost/127.0.0.1.')
}
export const AUTH_BROADCAST_STORAGE_KEY = 'prguard_auth_event'
export const AUTH_CHANGED_EVENT = 'auth:changed'

export const broadcastAuthChanged = (state = 'changed') => {
  if (!IS_BROWSER) return
  const payload = JSON.stringify({ state, ts: Date.now() })
  localStorage.setItem(AUTH_BROADCAST_STORAGE_KEY, payload)
  window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT, { detail: { state } }))
}

const client = axios.create({
  baseURL:         BASE_URL,
  headers:         { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout:         60000, 
})

let providerCache = 'claude'

const normalizeProvider = (provider) => {
  const normalized = (provider || '').trim().toLowerCase()
  if (normalized.includes('gemini')) return 'gemini'
  if (normalized.includes('gpt')) return 'gpt'
  if (normalized.includes('claude')) return 'claude'
  return normalized || 'claude'
}

export const getScopedProvider = () => providerCache

export const setScopedProvider = (provider) => {
  providerCache = normalizeProvider(provider)
}

// Legacy helpers kept for compatibility. API keys are never stored client-side.
export const getScopedApiKey = () => ''
export const setScopedApiKey = () => {}
export const clearScopedApiKey = () => {}


// ── Global 401 handler ────────────────────────────────────────────────────────
// Fires whenever any request gets a 401 so useAuth can react immediately
const extractError = (err) => {
  if (err?.code === 'ERR_CANCELED') return 'Request canceled by user.'
  const data = err?.response?.data
  // Prioritize detailed error message from backend
  const detail = data?.detail || data?.error
  if (detail) {
    return typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
  return err?.message || 'Unknown connection error.'
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const errorMsg = extractError(error)
    if (error?.response?.status === 401 && !errorMsg.toLowerCase().includes('api key')) {
      window.dispatchEvent(new CustomEvent('auth:expired'))
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
    const res = await client.post('/api/github/connect-repo', {
      repo_id: repoId,
      repo_name: repoName,
    })
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
      model: options.model || null,
      issue_number: issueNumber || null,
      history: history.filter(m => !m.isError),
    }, {
      signal: options.signal,
    })
    const payload = res.data || {}
    if (!payload.message && !payload.answer) {
      throw new Error('Invalid chat response format from server.')
    }
    const normalized = {
      ...payload,
      message: payload.message || payload.answer,
      answer: payload.answer || payload.message,
    }
    console.log('[Chat API] Response received', normalized)
    return normalized
  } catch (err) {
    const status = err?.response?.status;
    if (!status) {
      console.error('[Chat API] Network Error:', err)
    }
    if (err?.code === 'ERR_CANCELED') {
      throw new Error('Request canceled by user.')
    }
    const errorMsg = extractError(err)
    
    if (status === 502) {
      throw new Error('Backend server error (502). The application may be overloaded or restarting. Please try again in a moment.')
    } else if (status === 500) {
      throw new Error(`Server error: ${errorMsg}`)
    } else if (status === 401) {
      if (String(errorMsg).toLowerCase().includes('api key')) {
        throw new Error(errorMsg)
      }
      throw new Error('Session expired. Please sign in again.')
    } else if (status === 403) {
      throw new Error('Repository not connected. Connect the repository in Dashboard and retry.')
    } else if (status === 404) {
      throw new Error(errorMsg)
    } else if (status === 503) {
      throw new Error(`AI provider temporarily unavailable: ${errorMsg}`)
    } else if (status === 400) {
      throw new Error(`Invalid request: ${errorMsg}`)
    }
    
    throw new Error(errorMsg)
  }
}

export const getApiKeyStatus = async () => {
  const res = await client.get('/api/api-keys')
  const payload = res.data || { items: [], active_provider: 'claude', has_any_key: false }
  const active = normalizeProvider(payload.active_provider || 'claude')
  providerCache = active
  return {
    ...payload,
    active_provider: active,
  }
}

export const getUserProfile = async () => {
  const res = await client.get('/user/profile')
  const payload = res.data || {}
  const status = payload.api_key_status || { items: [], active_provider: 'claude', has_any_key: false }
  const active = normalizeProvider(status.active_provider || 'claude')
  providerCache = active
  return {
    ...payload,
    api_key_status: {
      ...status,
      active_provider: active,
    },
  }
}

export const saveApiKey = async (provider, apiKey, makeActive = true) => {
  const normalized = normalizeProvider(provider)
  console.log("SAVING KEY:", apiKey.slice(0, 10), "provider:", normalized)
  const res = await client.post('/api/api-keys', {
    provider: normalized,
    api_key: apiKey,
    make_active: makeActive,
  })
  console.log("SAVE RESPONSE:", res.status, res.data)
  if (makeActive) {
    providerCache = normalized
  }
  return res.data
}

export const deleteApiKey = async (provider) => {
  const normalized = normalizeProvider(provider)
  const res = await client.delete(`/api/api-keys/${normalized}`)
  if (normalized === providerCache) {
    try {
      await getApiKeyStatus()
    } catch {
      providerCache = normalizeProvider('claude')
    }
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
    // 🎭 Indexing needs extra patience (15 mins) for heavy CPU embeddings
    const res = await client.post('/api/index', { repo }, { timeout: 900000 })
    return res.data // { repo, files, chunks, indexed }
  } catch (err) {
    // Re-throw raw axios error so caller can read err.response.data.detail
    throw err
  }
}

export const pollIndexJob = async (jobId) => {
  try {
    const res = await client.get(`/api/index/job/${jobId}`)
    return res.data // { status: "queued" | "processing" | "completed" | "failed", progress, ... }
  } catch (err) {
    throw err
  }
}

// ── Index status ──────────────────────────────────────────────────────────────
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
      // Unauthenticated is an expected state during bootstrap.
      validateStatus: (status) => status === 200 || status === 401,
    })
    if (res.status === 401) {
      return null
    }
    return res.data
  } catch {
    return null
  }
}

export const logout = async () => {
  try {
    const res = await client.post('/auth/logout')
    broadcastAuthChanged('logged_out')
    return res.data || { redirect: '/login', role: 'user' }
  } catch {
    broadcastAuthChanged('logged_out')
    return { redirect: '/login', role: 'user' }
  }
}

export const adminLogin = async (identifier, password) => {
  const body = {
    email: identifier,
    password,
  }
  const res = await client.post('/admin/login', body)
  broadcastAuthChanged('logged_in')
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
    broadcastAuthChanged('logged_out')
    return res.data || { redirect: '/', role: 'admin' }
  } catch {
    broadcastAuthChanged('logged_out')
    return { redirect: '/', role: 'admin' }
  }
}

export const getAdminMe = async () => {
  const res = await client.get('/admin/me', {
    validateStatus: (status) => status === 200 || status === 401 || status === 403,
  })
  if (res.status !== 200) {
    return null
  }
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
