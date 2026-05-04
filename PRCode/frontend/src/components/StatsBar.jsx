import { useContext, useState, useEffect } from 'react'
import { ThemeContext } from '../App'
import { getTheme } from '../utils/helpers'
import { getApiKeyStatus, getScopedProvider } from '../api/client'

const PROVIDERS = [
  { id: 'claude', label: 'Claude Sonnet',  sub: 'Anthropic · Best for code' },
  { id: 'gpt',    label: 'GPT-4o',         sub: 'OpenAI · Most popular'      },
  { id: 'gemini', label: 'Gemini 1.5 Pro', sub: 'Google · Free tier'         },
]

export default function RepoList({
  repos,
  pinnedRepos = [],
  selectedRepo,
  onSelectRepo,
  onRemoveRepo = () => {},
  onTogglePin = () => {},
  onConnectClick,
  loading,
}) {
  const { theme } = useContext(ThemeContext)
  const t = getTheme(theme)
  const dark = theme === 'dark'

  // Theme-aware menu styles
  const panelBg   = dark ? '#161e28' : '#ffffff'
  const panelBord = dark ? '#2a3a50' : '#e2e2e2'

  const [activeProvider, setActiveProvider] = useState('claude')
  const [hasKey,         setHasKey]         = useState(false)
  const [hoveredRepo,    setHoveredRepo]    = useState(null)
  const [menuOpen,       setMenuOpen]       = useState(null) // ID of repo with open menu

  useEffect(() => {
    const read = async () => {
      const saved = getScopedProvider()
      const normalized = saved === 'gpt4o' ? 'gpt' : saved
      const status = await getApiKeyStatus().catch(() => ({ has_any_key: false }))
      if (normalized) setActiveProvider(normalized)
      setHasKey(Boolean(status?.has_any_key))
    }
    read()
    window.addEventListener('prguard:api-keys-updated', read)
    const interval = setInterval(read, 8000)
    return () => { window.removeEventListener('prguard:api-keys-updated', read); clearInterval(interval) }
  }, [])

  const providerLabel = PROVIDERS.find(p => p.id === activeProvider)?.label ?? 'No provider'

  // Sort repos: Pinned first
  const sorted = [...repos].sort((a, b) => {
    const ap = pinnedRepos.includes(a.name)
    const bp = pinnedRepos.includes(b.name)
    if (ap && !bp) return -1
    if (!ap && bp) return 1
    return 0
  })

  if (loading) return (
    <div className="space-y-1 p-2">
      {[1, 2, 3].map(i => (
        <div key={i} className="h-12 rounded animate-pulse" style={{ background: t.bg3 }} />
      ))}
    </div>
  )

  return (
    <div className="flex flex-col h-full" onClick={() => setMenuOpen(null)}>

      {/* Provider display */}
      <div style={{ borderBottom: `1px solid ${t.border}` }}>
        <div className="px-3 py-2 flex items-center justify-between" style={{ background: t.bg2 }}>
          <div className="flex items-center gap-2">
            <span style={{ color: hasKey ? '#22c55e' : '#f59e0b', fontSize: 7 }}>●</span>
            <span className="text-[11px] font-medium" style={{ color: t.accentText }}>{providerLabel}</span>
          </div>
          <span
            className="text-[10px] flex items-center gap-1 px-1.5 py-0.5 rounded"
            title="Change LLM provider"
            onClick={() => window.dispatchEvent(new CustomEvent('prguard:openApiPanel'))}
            style={{ color: dark ? '#94a3b8' : '#555', background: dark ? '#1e2a3a' : '#e8e8e8', border: `1px solid ${dark ? '#2a3a50' : '#d0d0d0'}`, cursor: 'pointer', userSelect: 'none' }}
            onMouseEnter={e => { e.currentTarget.style.background = dark ? '#2a3a50' : '#d8d8d8'; e.currentTarget.style.color = dark ? '#e2e8f0' : '#333' }}
            onMouseLeave={e => { e.currentTarget.style.background = dark ? '#1e2a3a' : '#e8e8e8'; e.currentTarget.style.color = dark ? '#94a3b8' : '#555' }}
          >
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
              <path d="M4.93 4.93a10 10 0 0 0 0 14.14"/>
            </svg>
            change
          </span>
        </div>
      </div>

      {/* Repo list */}
      <div className="flex-1 overflow-y-auto pt-1">
        {sorted.map(repo => {
          const isActive = selectedRepo === repo.name
          const isPinned = pinnedRepos.includes(repo.name)
          return (
            <div
              key={repo.id}
              onClick={() => onSelectRepo(repo.name)}
              onMouseEnter={() => setHoveredRepo(repo.id)}
              onMouseLeave={() => setHoveredRepo(null)}
              className="px-3 py-2.5 cursor-pointer border-l-2 transition-all relative group"
              style={{ borderLeftColor: isActive ? t.accent : 'transparent', background: isActive ? (dark ? '#1a2030' : '#fef3c7') : 'transparent' }}
            >
              <div className="flex items-center justify-between gap-1">
                <div className="flex items-center gap-1.5 flex-1 min-w-0">
                  {/* Star Indicator (Always visible if pinned) */}
                  {isPinned && (
                    <div style={{ color: '#eab308', display: 'flex' }}>
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                      </svg>
                    </div>
                  )}
                  <div className="text-xs font-medium truncate" style={{ color: isActive ? t.accentText : t.text2 }}>
                    {repo.name}
                  </div>
                </div>

                {/* More / Menu button */}
                {(hoveredRepo === repo.id || menuOpen === repo.id) && (
                  <div className="relative">
                    <button
                      onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === repo.id ? null : repo.id) }}
                      className="opacity-60 hover:opacity-100 p-0.5 rounded transition-all"
                      style={{ background: menuOpen === repo.id ? t.bg3 : 'none', border: 'none', color: t.text3, cursor: 'pointer' }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                        <circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/>
                      </svg>
                    </button>
                    
                    {menuOpen === repo.id && (
                      <div className="absolute right-0 top-6 z-[100] w-32 py-1 rounded-lg shadow-2xl" 
                           style={{ background: panelBg, border: `1px solid ${panelBord}`, boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
                        
                        {/* 1. Toggle Star (Pin) Action */}
                        <button
                          onClick={(e) => { e.stopPropagation(); onTogglePin(repo.name); setMenuOpen(null) }}
                          className="w-full text-left px-3 py-2 text-[10px] hover:bg-white/5 flex items-center gap-2"
                          style={{ color: t.text2, background: 'none', border: 'none', cursor: 'pointer' }}
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill={isPinned ? "currentColor" : "none"} stroke={isPinned ? "#eab308" : "currentColor"} strokeWidth="2.5" strokeLinecap="round">
                            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                          </svg>
                          {isPinned ? 'Unpin repo' : 'Pin to top'}
                        </button>

                        <div style={{ height: 1, background: t.border, margin: '2px 0' }} />

                        {/* 2. Remove Action (Red) */}
                        <button
                          onClick={(e) => { e.stopPropagation(); onRemoveRepo(repo.name); setMenuOpen(null) }}
                          className="w-full text-left px-3 py-2 text-[10px] hover:bg-red-500/10 flex items-center gap-2"
                          style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer' }}
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                            <path d="M3 6h18m-2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                          </svg>
                          Remove repo
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 text-[10px] mt-1" style={{ color: t.text3 }}>
                <span className="opacity-70">{repo.language}</span>
                {repo.stars > 0 && <span>★ {(repo.stars / 1000).toFixed(1)}k</span>}
                {repo.indexed && <span className="ml-auto flex items-center gap-1" style={{ color: t.accentText }}>
                  <div className="w-1 h-1 rounded-full bg-blue-500"/> indexed
                </span>}
              </div>
            </div>
          )
        })}

        {/* + Connect Repository button */}
        <div
          onClick={onConnectClick}
          className="mx-3 mt-4 rounded-lg px-3 py-2.5 text-xs text-center cursor-pointer transition-all border border-dashed flex items-center justify-center gap-2"
          style={{ borderColor: t.border, color: t.text3, background: dark ? '#0a0e13' : '#f9f9f9' }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = t.accent; e.currentTarget.style.color = t.accentText; e.currentTarget.style.background = t.accent + '10' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.text3; e.currentTarget.style.background = dark ? '#0a0e13' : '#f9f9f9' }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Connect Repository
        </div>
      </div>
    </div>
  )
}

export const timeAgo = (dateString) => {
  const date = new Date(dateString)
  const now = new Date()
  const seconds = Math.floor((now - date) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export const truncate = (str, length = 50) => {
  if (!str) return ''
  return str.length > length ? str.substring(0, length) + '...' : str
}