import { useState, useContext, useEffect, useCallback, useRef } from 'react'
import { ThemeContext } from '../App'
import { getTheme } from '../utils/helpers'
import Navbar from '../components/Navbar'
import RepoList from '../components/StatsBar'
import IssueList from '../components/ActivityFeed'
import FileTree from '../components/ReviewCard'
import ChatPanel, { ConnectRepoModal } from '../components/ChatPanel'
import { useRepos, useIssues, useFiles } from '../hooks/useReviews'
import {
  deleteApiKey,
  getApiKeyStatus,
  getScopedProvider,
  saveApiKey,
  setActiveProvider,
  setScopedProvider,
} from '../api/client'

const PROVIDER_LIST = [
  { id: 'claude', label: 'Claude Sonnet',  sub: 'Anthropic · Best for code',   placeholder: 'sk-ant-...', recommended: true  },
  { id: 'gpt',    label: 'GPT-4o',         sub: 'OpenAI · Most popular',        placeholder: 'sk-...',     recommended: false },
  { id: 'gemini', label: 'Gemini 1.5 Pro', sub: 'Google · Free tier available', placeholder: 'AIza...',    recommended: false },
]
const PROVIDER_NAMES = { claude: 'Claude Sonnet', gpt: 'GPT-4o', gemini: 'Gemini 1.5 Pro' }

function ResizeHandle({ onMouseDown, dark }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseDown={onMouseDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: 4,
        flexShrink: 0,
        cursor: 'col-resize',
        background: hovered ? '#d97706' : 'transparent',
        borderRight: `1px solid ${dark ? '#1e2a3a' : '#e0e0e0'}`,
        transition: 'background 0.15s',
        position: 'relative',
        zIndex: 10,
        userSelect: 'none',
      }}
      title="Drag to resize"
    >
      <div style={{ position: 'absolute', inset: '0 -3px', cursor: 'col-resize' }} />
    </div>
  )
}

function EyeIcon({ open }) {
  return open ? (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ) : (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  )
}

export default function Dashboard() {
  const { theme } = useContext(ThemeContext)
  const t = getTheme(theme)
  const dark = theme === 'dark'

  const [repoWidth,  setRepoWidth]  = useState(208)
  const [issueWidth, setIssueWidth] = useState(224)
  const MIN_W = 120
  const MAX_W = 400
  const containerRef = useRef(null)

  const startResize = useCallback((which, e) => {
    e.preventDefault()
    const startX    = e.clientX
    const startRepo = repoWidth
    const startIssue = issueWidth

    const onMove = (ev) => {
      const dx = ev.clientX - startX
      if (which === 'repo') {
        setRepoWidth(Math.min(MAX_W, Math.max(MIN_W, startRepo + dx)))
      } else {
        setIssueWidth(Math.min(MAX_W, Math.max(MIN_W, startIssue + dx)))
      }
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [repoWidth, issueWidth])

  const [selectedRepo,  setSelectedRepo]  = useState(null)
  const [pendingRepo,   setPendingRepo]   = useState(null)
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [leftTab,       setLeftTab]       = useState('issues')
  const [chatInput,     setChatInput]     = useState('')
  const [autoSend,      setAutoSend]      = useState(false)
  const [providerLabel, setProviderLabel] = useState('No provider')
  const [apiPanelError, setApiPanelError] = useState('')

  useEffect(() => {
    const read = () => {
      const id = getScopedProvider()
      setProviderLabel(id ? (PROVIDER_NAMES[id] ?? id) : 'No provider')
    }
    read()
    window.addEventListener('storage', read)
    const timer = setInterval(read, 1500)
    return () => { window.removeEventListener('storage', read); clearInterval(timer) }
  }, [])

  const { issues, setIssues, loading: issuesLoading } = useIssues(selectedRepo)
  const { files,  loading: filesLoading  } = useFiles(selectedRepo)

  const handleRepoSelect = useCallback((repoName) => {
    if (repoName === selectedRepo) return
    if (!selectedRepo) {
      setSelectedRepo(repoName)
      setSelectedIssue(null)
      setChatInput('')
      setAutoSend(false)
      return
    }
    setPendingRepo(repoName)
  }, [selectedRepo])

  const confirmSwitch = () => {
    setSelectedRepo(pendingRepo)
    setSelectedIssue(null)
    setChatInput('')
    setAutoSend(false)
    setPendingRepo(null)
  }

  const handleIssueSelect = useCallback((issue) => {
    setSelectedIssue(issue)
    setChatInput(`Explain issue #${issue.number}: "${issue.title}". Which files are responsible and how do I fix it?`)
    setAutoSend(false)
  }, [])

  const handleFileSelect = useCallback((filePath) => {
    setChatInput(`Explain what ${filePath} does and how it connects to the rest of the codebase.`)
    setAutoSend(false)
  }, [])

  const [pinnedRepos, setPinnedRepos] = useState(() => {
    const saved = localStorage.getItem('prguard_pinned')
    if (!saved) return []
    try { return JSON.parse(saved) } catch { localStorage.removeItem('prguard_pinned'); return [] }
  })

  useEffect(() => {
    localStorage.setItem('prguard_pinned', JSON.stringify(pinnedRepos))
  }, [pinnedRepos])

  const [hiddenRepos, setHiddenRepos] = useState(() => {
    const saved = localStorage.getItem('prguard_hidden')
    if (!saved) return []
    try { return JSON.parse(saved) } catch { localStorage.removeItem('prguard_hidden'); return [] }
  })

  useEffect(() => {
    localStorage.setItem('prguard_hidden', JSON.stringify(hiddenRepos))
  }, [hiddenRepos])

  const { repos: fetchedRepos, loading: reposLoading, refresh: refreshRepos } = useRepos()

  const handleRepoConnect = useCallback(async (newRepo) => {
    await refreshRepos()
    setHiddenRepos(prev => prev.filter(name => name !== newRepo.name))
    setSelectedRepo(newRepo.name)
    setSelectedIssue(null)
    setChatInput('')
    setPendingRepo(null)
  }, [refreshRepos])

  const handleRemoveRepo = useCallback(async (repoName) => {
    try {
      const { disconnectRepo } = await import('../api/client')
      const repoToDisconnect = fetchedRepos.find(r => r.name === repoName)
      if (!repoToDisconnect) { alert('Repository not found in connected list'); return }
      await disconnectRepo(repoToDisconnect.id)
      await refreshRepos()
      setPinnedRepos(prev => prev.filter(name => name !== repoName))
      setHiddenRepos(prev => prev.filter(name => name !== repoName))
      if (selectedRepo === repoName) { setSelectedRepo(null); setSelectedIssue(null) }
    } catch (err) {
      alert('Failed to disconnect repository')
    }
  }, [fetchedRepos, selectedRepo, refreshRepos])

  const handleTogglePin = useCallback((repoName) => {
    setPinnedRepos(prev => {
      if (prev.includes(repoName)) return prev.filter(n => n !== repoName)
      return [...prev, repoName]
    })
  }, [])

  const allRepos = fetchedRepos
  const sortedRepos = [...allRepos].sort((a, b) => {
    const aPinned = pinnedRepos.includes(a.name)
    const bPinned = pinnedRepos.includes(b.name)
    if (aPinned && !bPinned) return -1
    if (!aPinned && bPinned) return 1
    return 0
  })

  // ── API panel ─────────────────────────────────────────────────────────────
  const [apiPanelOpen, setApiPanelOpen] = useState(false)
  const [apiKeys,      setApiKeys]      = useState({ claude: '', gpt: '', gemini: '' })
  const [showKeys,     setShowKeys]     = useState({ claude: false, gpt: false, gemini: false })
  const [savedKeys,    setSavedKeys]    = useState({ claude: false, gpt: false, gemini: false })
  const [connected,    setConnected]    = useState({ claude: false, gpt: false, gemini: false })
  const [activeId,     setActiveId]     = useState('claude')

  const refreshApiStatus = useCallback(async () => {
    try {
      const status = await getApiKeyStatus()
      const nextConnected = { claude: false, gpt: false, gemini: false }
      const masked = { claude: '', gpt: '', gemini: '' }
      ;(status.items || []).forEach((item) => {
        if (item?.provider && Object.prototype.hasOwnProperty.call(nextConnected, item.provider)) {
          nextConnected[item.provider] = Boolean(item.has_key)
          masked[item.provider] = item.masked_key || ''
        }
      })
      const active = status.active_provider || 'claude'
      setConnected(nextConnected)
      // ✅ Don't overwrite apiKeys with masked values — only update connected/active state
      setActiveId(active)
      setScopedProvider(active)
      setProviderLabel(PROVIDER_NAMES[active] ?? active)
      setApiPanelError('')
    } catch (err) {
      setApiPanelError(err?.response?.data?.detail || err?.message || 'Failed to load API key status')
    }
  }, [])

  useEffect(() => {
    refreshApiStatus()
  }, [refreshApiStatus])

  // ✅ Clear input fields and refresh status every time panel opens
  useEffect(() => {
    if (apiPanelOpen) {
      setApiKeys({ claude: '', gpt: '', gemini: '' })
      refreshApiStatus()
    }
  }, [apiPanelOpen, refreshApiStatus])

  useEffect(() => {
    const handler = () => setApiPanelOpen(true)
    window.addEventListener('prguard:openApiPanel', handler)
    return () => window.removeEventListener('prguard:openApiPanel', handler)
  }, [])

  const [connectModalOpen, setConnectModalOpen] = useState(false)
  useEffect(() => {
    const handler = () => setConnectModalOpen(true)
    window.addEventListener('prguard:openConnect', handler)
    return () => window.removeEventListener('prguard:openConnect', handler)
  }, [])

  // ✅ Fixed: only block if key is empty or contains '...' (masked value)
  const handleApiSave = async (providerId) => {
    const key = apiKeys[providerId]
    if (!key || key === '') return
    if (key.includes('...')) return
    try {
      await saveApiKey(providerId, key, true)
      await refreshApiStatus()
      window.dispatchEvent(new CustomEvent('prguard:api-keys-updated'))
      setSavedKeys(prev => ({ ...prev, [providerId]: true }))
      setTimeout(() => setSavedKeys(prev => ({ ...prev, [providerId]: false })), 1500)
    } catch (err) {
      setApiPanelError(err?.response?.data?.detail || err?.message || 'Failed to save API key')
    }
  }

  const handleSetActiveProvider = async (providerId) => {
    if (!connected[providerId]) return
    try {
      await setActiveProvider(providerId)
      await refreshApiStatus()
      window.dispatchEvent(new CustomEvent('prguard:api-keys-updated'))
    } catch (err) {
      setApiPanelError(err?.response?.data?.detail || err?.message || 'Failed to switch provider')
    }
  }

  const handleDeleteApiKey = async (providerId) => {
    const confirmed = window.confirm(`Remove ${PROVIDER_NAMES[providerId] ?? providerId} API key?`)
    if (!confirmed) return
    try {
      await deleteApiKey(providerId)
      await refreshApiStatus()
      window.dispatchEvent(new CustomEvent('prguard:api-keys-updated'))
    } catch (err) {
      setApiPanelError(err?.response?.data?.detail || err?.message || 'Failed to remove API key')
    }
  }

  const connectedCount = Object.values(connected).filter(Boolean).length
  const anyConnected   = connectedCount > 0
  const panelBg   = dark ? '#0f1318' : '#ffffff'
  const panelBord = dark ? '#1e2a3a' : '#e2e2e2'
  const rowBord   = dark ? '#161e28' : '#f2f2f2'
  const inputBg   = dark ? '#0a0e13' : '#f5f5f5'
  const mutedText = dark ? '#6b7280' : '#888'
  const eyeColor  = dark ? '#94a3b8' : '#666'

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: t.bg, color: t.text }}>
      <Navbar />

      <div ref={containerRef} style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>

        <div style={{ width: repoWidth, minWidth: repoWidth, maxWidth: repoWidth, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: t.bg2 }}>
          <div style={{ padding: '8px 12px', flexShrink: 0, borderBottom: `1px solid ${t.border}` }}>
            <p style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.1em', color: t.text3, margin: 0 }}>Repositories</p>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
            <RepoList
              repos={sortedRepos}
              pinnedRepos={pinnedRepos}
              selectedRepo={selectedRepo}
              onSelectRepo={handleRepoSelect}
              onRemoveRepo={handleRemoveRepo}
              onTogglePin={handleTogglePin}
              onConnectClick={() => window.dispatchEvent(new CustomEvent('prguard:openConnect'))}
              loading={reposLoading}
            />
          </div>
        </div>

        <ResizeHandle dark={dark} onMouseDown={(e) => startResize('repo', e)} />

        <div style={{ width: issueWidth, minWidth: issueWidth, maxWidth: issueWidth, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: t.bg2 }}>
          <div style={{ display: 'flex', flexShrink: 0, borderBottom: `1px solid ${t.border}` }}>
            {['issues', 'files'].map(tab => (
              <button key={tab} onClick={() => setLeftTab(tab)}
                style={{ flex: 1, padding: '8px 0', fontSize: 10, textTransform: 'capitalize', letterSpacing: '0.06em', border: 'none', borderBottom: `2px solid ${leftTab === tab ? t.accent : 'transparent'}`, color: leftTab === tab ? t.accentText : t.text3, background: 'transparent', cursor: 'pointer', transition: 'all 0.15s' }}>
                {tab}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
            {leftTab === 'issues'
              ? <IssueList issues={issues} setIssues={setIssues} selectedRepo={selectedRepo} selectedIssue={selectedIssue} onSelectIssue={handleIssueSelect} loading={issuesLoading} />
              : <FileTree  files={files}   onFileSelect={handleFileSelect} />
            }
          </div>
        </div>

        <ResizeHandle dark={dark} onMouseDown={(e) => startResize('issue', e)} />

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          <ChatPanel
            selectedRepo={selectedRepo}
            selectedIssue={selectedIssue}
            chatInput={chatInput}
            setChatInput={setChatInput}
            autoSend={autoSend}
            setAutoSend={setAutoSend}
            onRepoConnect={handleRepoConnect}
          />
        </div>
      </div>

      {/* ── Status bar ── */}
      <div style={{ height: 26, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 16, padding: '0 16px', background: dark ? '#0d1117' : '#f0f0f0', borderTop: `1px solid ${dark ? '#1e2530' : '#d0d0d0'}`, fontSize: 10, position: 'relative', zIndex: 50 }}>
        <span style={{ fontWeight: 600, letterSpacing: '0.05em', color: t.accentText, fontFamily: 'monospace' }}>PRGuard</span>
        <span style={{ color: dark ? '#1e2530' : '#ccc' }}>·</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#22c55e' }}>
          <span style={{ fontSize: 7 }}>●</span> RAG Active
        </span>
        <span style={{ color: dark ? '#1e2530' : '#ccc' }}>·</span>
        <span style={{ color: mutedText }}>{selectedRepo}</span>
        {selectedIssue && (
          <>
            <span style={{ color: dark ? '#1e2530' : '#ccc' }}>·</span>
            <span style={{ color: mutedText }}>Issue #{selectedIssue.number}</span>
          </>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: mutedText }}>{providerLabel}</span>
          <span style={{ color: dark ? '#1e2530' : '#ccc' }}>·</span>
          <span style={{ color: mutedText }}>ChromaDB</span>
          <span style={{ color: dark ? '#1e2530' : '#ccc' }}>·</span>

          <div style={{ position: 'relative' }}>
            <button onClick={() => setApiPanelOpen(p => !p)}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: 'none', cursor: 'pointer', padding: '2px 6px', color: anyConnected ? '#22c55e' : '#f59e0b', borderRadius: 4 }}
              onMouseEnter={e => e.currentTarget.style.background = dark ? '#1a2030' : '#e0e0e0'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="7.5" cy="15.5" r="5.5"/><path d="M21 2l-9.6 9.6"/><path d="M15.5 7.5l3 3L22 7l-3-3"/>
              </svg>
              <span style={{ fontSize: 10, fontWeight: 500 }}>{anyConnected ? `${connectedCount} key${connectedCount > 1 ? 's' : ''} set` : 'Set API key'}</span>
              <span style={{ fontSize: 8, opacity: 0.5 }}>{apiPanelOpen ? '▴' : '▾'}</span>
            </button>

            {apiPanelOpen && (
              <div style={{ position: 'absolute', bottom: '100%', right: 0, marginBottom: 8, width: 292, background: panelBg, border: `1px solid ${panelBord}`, borderRadius: 10, overflow: 'hidden', boxShadow: dark ? '0 -8px 32px rgba(0,0,0,0.75)' : '0 -4px 24px rgba(0,0,0,0.15)', zIndex: 9999 }}>
                <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${rowBord}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: t.text }}>LLM Provider</span>
                    <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: anyConnected ? '#22c55e22' : '#f59e0b22', color: anyConnected ? '#22c55e' : '#f59e0b', border: `1px solid ${anyConnected ? '#22c55e55' : '#f59e0b55'}` }}>
                      {connectedCount}/{PROVIDER_LIST.length} connected
                    </span>
                  </div>
                  <button onClick={() => setApiPanelOpen(false)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: mutedText, fontSize: 16, lineHeight: 1, padding: '0 2px' }}
                    onMouseEnter={e => e.currentTarget.style.color = t.text}
                    onMouseLeave={e => e.currentTarget.style.color = mutedText}>×</button>
                </div>

                {PROVIDER_LIST.map(provider => (
                  <div key={provider.id} style={{ padding: '10px 12px', borderBottom: `1px solid ${rowBord}` }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 5, height: 5, borderRadius: '50%', display: 'inline-block', flexShrink: 0, background: connected[provider.id] ? '#22c55e' : '#374151' }}/>
                        <span style={{ fontSize: 11, fontWeight: 500, color: t.text }}>{provider.label}</span>
                        {provider.recommended && <span style={{ fontSize: 8, padding: '0 4px', borderRadius: 3, color: t.accentText, background: t.accent + '20' }}>recommended</span>}
                        {provider.id === 'gemini' && <span style={{ fontSize: 8, padding: '0 4px', borderRadius: 3, color: '#22c55e', background: '#22c55e20' }}>free tier</span>}
                      </div>
                      {connected[provider.id] && activeId === provider.id && <span style={{ fontSize: 9, color: '#22c55e' }}>● active</span>}
                    </div>
                    <div style={{ fontSize: 9, color: mutedText, marginBottom: 6 }}>{provider.sub}</div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <div style={{ display: 'flex', flex: 1, minWidth: 0, borderRadius: 4, overflow: 'hidden', border: `1px solid ${connected[provider.id] ? '#22c55e55' : panelBord}`, background: inputBg }}>
                        <input
                          type={showKeys[provider.id] ? 'text' : 'password'}
                          value={apiKeys[provider.id]}
                          onChange={e => setApiKeys(prev => ({ ...prev, [provider.id]: e.target.value }))}
                          onKeyDown={e => { if (e.key === 'Enter') handleApiSave(provider.id) }}
                          placeholder={connected[provider.id] ? '••••••••••••' : provider.placeholder}
                          style={{ flex: 1, minWidth: 0, padding: '4px 7px', fontSize: 10, fontFamily: 'monospace', background: 'transparent', border: 'none', color: t.text, outline: 'none' }}
                        />
                        <button type="button" onClick={() => setShowKeys(prev => ({ ...prev, [provider.id]: !prev[provider.id] }))}
                          style={{ padding: '0 8px', background: 'transparent', border: 'none', cursor: 'pointer', color: eyeColor, display: 'flex', alignItems: 'center', flexShrink: 0 }}
                          onMouseEnter={e => e.currentTarget.style.color = t.text}
                          onMouseLeave={e => e.currentTarget.style.color = eyeColor}>
                          <EyeIcon open={showKeys[provider.id]} />
                        </button>
                      </div>
                      <button onClick={() => handleApiSave(provider.id)} disabled={!apiKeys[provider.id]}
                        style={{ padding: '4px 10px', fontSize: 10, fontWeight: 500, borderRadius: 4, flexShrink: 0, transition: 'all 0.15s', cursor: apiKeys[provider.id] ? 'pointer' : 'not-allowed', border: `1px solid ${savedKeys[provider.id] ? '#22c55e' : apiKeys[provider.id] ? t.accent : panelBord}`, background: savedKeys[provider.id] ? '#22c55e22' : apiKeys[provider.id] ? t.accentBg : inputBg, color: savedKeys[provider.id] ? '#22c55e' : apiKeys[provider.id] ? t.accentFg : mutedText }}>
                        {savedKeys[provider.id] ? '✓' : connected[provider.id] ? 'Update' : 'Save'}
                      </button>
                      <button onClick={() => handleSetActiveProvider(provider.id)} disabled={!connected[provider.id]}
                        style={{ padding: '4px 8px', fontSize: 10, borderRadius: 4, border: `1px solid ${panelBord}`, background: activeId === provider.id ? '#22c55e22' : inputBg, color: activeId === provider.id ? '#22c55e' : mutedText, cursor: connected[provider.id] ? 'pointer' : 'not-allowed' }}>
                        Active
                      </button>
                      <button onClick={() => handleDeleteApiKey(provider.id)} disabled={!connected[provider.id]}
                        style={{ padding: '4px 8px', fontSize: 10, borderRadius: 4, border: `1px solid #ef444466`, background: dark ? '#2a1010' : '#fee2e2', color: '#ef4444', cursor: connected[provider.id] ? 'pointer' : 'not-allowed' }}>
                        Remove
                      </button>
                    </div>
                  </div>
                ))}

                {apiPanelError && (
                  <div style={{ padding: '8px 12px', fontSize: 10, color: '#ef4444', borderTop: `1px solid ${rowBord}` }}>
                    {apiPanelError}
                  </div>
                )}

                <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: dark ? '#0a0d11' : '#fafafa' }}>
                  <span style={{ fontSize: 9, color: mutedText }}>🔒 Stored securely on server</span>
                  <span style={{ fontSize: 9, color: mutedText }}>Claude · GPT-4o · Gemini</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {pendingRepo && (
        <div style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 99999, background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(3px)' }}>
          <div style={{ width: 380, background: dark ? '#0f1318' : '#fff', border: `1px solid ${dark ? '#1e2a3a' : '#e2e2e2'}`, borderRadius: 12, overflow: 'hidden', boxShadow: '0 24px 64px rgba(0,0,0,0.6)' }}>
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${dark ? '#161e28' : '#f0f0f0'}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
                <span style={{ fontSize: 14, fontWeight: 600, color: t.text }}>Switch Repository?</span>
              </div>
              <p style={{ fontSize: 11, color: mutedText, margin: 0 }}>
                Leaving <span style={{ color: t.accentText, fontFamily: 'monospace' }}>{selectedRepo}</span>
              </p>
            </div>
            <div style={{ padding: '16px 20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, padding: 12, borderRadius: 8, background: dark ? '#0a0e13' : '#f8f8f8', border: `1px solid ${dark ? '#1e2a3a' : '#e8e8e8'}` }}>
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: mutedText, marginBottom: 3, textTransform: 'uppercase' }}>Current</div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: t.text3, fontFamily: 'monospace' }}>{selectedRepo}</div>
                </div>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={mutedText} strokeWidth="2" strokeLinecap="round"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: mutedText, marginBottom: 3, textTransform: 'uppercase' }}>Switching to</div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: t.accentText, fontFamily: 'monospace' }}>{pendingRepo}</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 16, padding: '8px 12px', borderRadius: 8, background: '#f59e0b11', border: '1px solid #f59e0b33' }}>
                <span style={{ fontSize: 12, color: '#f59e0b', flexShrink: 0 }}>⚠</span>
                <p style={{ fontSize: 11, color: '#f59e0b', lineHeight: 1.5, margin: 0 }}>Chat history and selected issue will be cleared.</p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => setPendingRepo(null)}
                  style={{ flex: 1, padding: '8px', borderRadius: 8, fontSize: 12, fontWeight: 500, background: 'transparent', border: `1px solid ${dark ? '#1e2a3a' : '#e2e2e2'}`, color: mutedText, cursor: 'pointer', transition: 'all 0.15s' }}
                  onMouseEnter={e => { e.currentTarget.style.background = dark ? '#1a2030' : '#f0f0f0'; e.currentTarget.style.color = t.text }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = mutedText }}>
                  Cancel
                </button>
                <button onClick={confirmSwitch}
                  style={{ flex: 1, padding: '8px', borderRadius: 8, fontSize: 12, fontWeight: 500, background: t.accentBg, border: `1px solid ${t.accent}`, color: t.accentFg, cursor: 'pointer', transition: 'all 0.15s' }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
                  onMouseLeave={e => e.currentTarget.style.opacity = '1'}>
                  Switch to {pendingRepo.split('/')[1]}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {connectModalOpen && (
        <ConnectRepoModal
          t={t}
          dark={dark}
          onClose={() => setConnectModalOpen(false)}
          onConnect={handleRepoConnect}
        />
      )}
    </div>
  )
}
