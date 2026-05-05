import axios from 'axios'

// In production, set VITE_API_BASE_URL (for example: https://api.yourdomain.com).
// In development, keep it empty to use the Vite proxy.
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

let providerCache = 'claude'

const normalizeProvider = (provider) => {
  const normalized = (provider || '').trim().toLowerCase()
  if (normalized === 'gpt4o') return 'gpt'
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
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
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

export const toggleWorkingOn = async (issueNumber, repo, active) => {
  try {
    const res = await client.post(`/api/issues/${issueNumber}/working-on`, {
      repo,
      active
    })
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
    console.error('[Chat API] Error:', err)
    if (err?.code === 'ERR_CANCELED') {
      throw new Error('Request canceled by user.')
    }
    const status = err?.response?.status
    const errorMsg = err?.response?.data?.detail || err?.message || 'Connection error. Check your settings.'
    
    if (status === 502) {
      throw new Error('Backend server error (502). The application may be overloaded or restarting. Please try again in a moment.')
    } else if (status === 500) {
      throw new Error(`Server error: ${errorMsg}`)
    } else if (status === 401) {
      throw new Error('Session expired. Please sign in again.')
    } else if (status === 403) {
      throw new Error('Repository not connected. Connect the repository in Dashboard and retry.')
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

export const saveUserApiKey = async (provider, apiKey, makeActive = true) => {
  const normalized = normalizeProvider(provider)
  const res = await client.post('/user/api-key', {
    provider: normalized,
    api_key: apiKey,
    make_active: makeActive,
  })
  if (makeActive) {
    providerCache = normalized
  }
  return res.data
}

export const saveApiKey = async (provider, apiKey, makeActive = true) => {
  const normalized = normalizeProvider(provider)
  const res = await client.put(`/api/api-keys/${normalized}`, {
    api_key: apiKey,
    make_active: makeActive,
  })
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
    localStorage.removeItem('prguard_session') // ✅ add this
    const res = await client.post('/auth/logout')
    return res.data || { redirect: '/login', role: 'user' }
  } catch {
    return { redirect: '/login', role: 'user' }
  }
}

export const adminLogin = async (identifier, password) => {
  const body = {
    email: identifier,
    password,
  }
  const res = await client.post('/admin/login', body)
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
