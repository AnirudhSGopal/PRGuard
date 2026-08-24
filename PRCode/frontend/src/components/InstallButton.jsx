import { useContext, useState, useEffect, useRef } from 'react'
import { ThemeContext } from '../App'
import { getTheme } from '../utils/helpers'
import {
  getScopedApiKey,
  getScopedProvider,
  setScopedApiKey,
  setScopedProvider,
} from '../api/client'

const PROVIDERS = [
  {
    id: 'claude',
    label: 'Claude Sonnet',
    sub: 'Anthropic · Best for code',
    placeholder: 'sk-ant-...',
    recommended: true,
  },
  {
    id: 'gpt4o',
    label: 'GPT-4o',
    sub: 'OpenAI · Most popular',
    placeholder: 'sk-...',
    recommended: false,
  },
  {
    id: 'gemini',
    label: 'Gemini 1.5 Pro',
    sub: 'Google · Free tier available',
    placeholder: 'AIza...',
    recommended: false,
  },
]

/**
 * InstallButton
 * A self-contained API key manager button.
 * Renders a small pill in the status bar; clicking opens a floating panel above it.
 *
 * Props:
 *   onProviderChange(providerId, apiKey) — called whenever a key is saved
 */
export default function InstallButton({ onProviderChange }) {
  const { theme } = useContext(ThemeContext)
  const t = getTheme(theme)

  const [open, setOpen] = useState(false)
  const [apiKeys, setApiKeys] = useState({ claude: '', gpt4o: '', gemini: '' })
  const [savedKeys, setSavedKeys] = useState({ claude: false, gpt4o: false, gemini: false })
  const [connected, setConnected] = useState({ claude: false, gpt4o: false, gemini: false })
  const [activeProvider, setActiveProvider] = useState('claude')
  const ref = useRef(null)
  const saveTimeoutsRef = useRef({})

  // Load persisted keys
  useEffect(() => {
    const provider = getScopedProvider()
    const key = getScopedApiKey()
    if (provider && key) {
      setActiveProvider(provider)
      setApiKeys(prev => ({ ...prev, [provider]: key }))
      setConnected(prev => ({ ...prev, [provider]: true }))
    }
  }, [])

  // Click outside closes panel
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    return () => {
      Object.values(saveTimeoutsRef.current).forEach((timeoutId) => {
        if (timeoutId) clearTimeout(timeoutId)
      })
    }
  }, [])

  const handleSave = (providerId) => {
    const key = apiKeys[providerId]
    if (!key) return
    setScopedProvider(providerId)
    setScopedApiKey(key)
    setActiveProvider(providerId)
    setConnected(prev => ({ ...prev, [providerId]: true }))
    setSavedKeys(prev => ({ ...prev, [providerId]: true }))
    onProviderChange?.(providerId, key)
    if (saveTimeoutsRef.current[providerId]) {
      clearTimeout(saveTimeoutsRef.current[providerId])
    }
    saveTimeoutsRef.current[providerId] = setTimeout(() => {
      setSavedKeys(prev => ({ ...prev, [providerId]: false }))
    }, 1500)
  }

  const connectedCount = Object.values(connected).filter(Boolean).length
  const anyConnected = connectedCount > 0

  // ── colours that work for both bar placement ──
  const dark = theme === 'dark'
  const panelBg     = dark ? '#0f1318' : '#ffffff'
  const panelBorder = dark ? '#1e2a3a' : '#e2e2e2'
  const rowBorder   = dark ? '#161e28' : '#f2f2f2'
  const inputBg     = dark ? '#0a0e13' : '#f5f5f5'
  const mutedText   = dark ? '#4a5568' : '#888'
  const hoverBg     = dark ? '#1a2030' : '#e8e8e8'

  return (
    <div className="relative flex items-center" ref={ref}>

      {/* ── PILL BUTTON ── */}
      <button
        onClick={() => setOpen(prev => !prev)}
        className="flex items-center gap-1.5 transition-all rounded"
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: '2px 6px',
          color: anyConnected ? '#22c55e' : '#f59e0b',
        }}
        onMouseEnter={e => e.currentTarget.style.background = hoverBg}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        title="Manage API Keys"
      >
        {/* Key icon SVG */}
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="7.5" cy="15.5" r="5.5" />
          <path d="M21 2l-9.6 9.6" />
          <path d="M15.5 7.5l3 3L22 7l-3-3" />
        </svg>
        <span style={{ fontSize: 10, fontWeight: 500 }}>
          {anyConnected ? `${connectedCount} key${connectedCount > 1 ? 's' : ''} set` : 'Set API key'}
        </span>
        <span style={{ fontSize: 8, opacity: 0.5 }}>
          {open ? '▴' : '▾'}
        </span>
      </button>

      {/* ── FLOATING PANEL (opens upward) ── */}
      {open && (
        <div
          className="absolute bottom-full right-0 mb-2 rounded-lg overflow-hidden"
          style={{
            width: 280,
            background: panelBg,
            border: `1px solid ${panelBorder}`,
            boxShadow: dark
              ? '0 -8px 32px rgba(0,0,0,0.7)'
              : '0 -4px 24px rgba(0,0,0,0.13)',
            zIndex: 9999,
          }}
        >
          {/* Header */}
          <div
            className="px-3 py-2 flex items-center justify-between"
            style={{ borderBottom: `1px solid ${rowBorder}` }}
          >
            <div className="flex items-center gap-2">
              <span style={{
                fontSize: 10, fontWeight: 600, letterSpacing: '0.05em',
                textTransform: 'uppercase', color: t.text,
              }}>
                LLM Provider
              </span>
              <span style={{
                fontSize: 9, padding: '1px 5px', borderRadius: 3,
                background: anyConnected ? '#22c55e22' : '#f59e0b22',
                color: anyConnected ? '#22c55e' : '#f59e0b',
                border: `1px solid ${anyConnected ? '#22c55e44' : '#f59e0b44'}`,
              }}>
                {connectedCount}/{PROVIDERS.length} connected
              </span>
            </div>
            <button
              onClick={() => setOpen(false)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: mutedText, fontSize: 16, lineHeight: 1, padding: '0 2px',
              }}
              onMouseEnter={e => e.currentTarget.style.color = t.text}
              onMouseLeave={e => e.currentTarget.style.color = mutedText}
            >
              ×
            </button>
          </div>

          {/* Provider rows */}
          {PROVIDERS.map((provider) => (
            <div
              key={provider.id}
              className="px-3 py-2.5"
              style={{ borderBottom: `1px solid ${rowBorder}` }}
            >
              {/* Provider name + badges */}
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <span style={{
                    width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                    background: connected[provider.id] ? '#22c55e' : '#374151',
                    display: 'inline-block',
                  }} />
                  <span style={{ fontSize: 11, fontWeight: 500, color: t.text }}>
                    {provider.label}
                  </span>
                  {provider.recommended && (
                    <span style={{
                      fontSize: 8, padding: '0 4px', borderRadius: 3,
                      color: t.accentText, background: t.accent + '20',
                    }}>
                      recommended
                    </span>
                  )}
                  {provider.id === 'gemini' && (
                    <span style={{
                      fontSize: 8, padding: '0 4px', borderRadius: 3,
                      color: '#22c55e', background: '#22c55e20',
                    }}>
                      free tier
                    </span>
                  )}
                </div>
                {connected[provider.id] && activeProvider === provider.id && (
                  <span style={{ fontSize: 9, color: '#22c55e' }}>● active</span>
                )}
              </div>

              {/* Sub label */}
              <div style={{ fontSize: 9, color: mutedText, marginBottom: 6 }}>
                {provider.sub}
              </div>

              {/* Input + Save */}
              <div className="flex gap-1.5">
                <input
                  type="password"
                  value={apiKeys[provider.id]}
                  onChange={e => setApiKeys(prev => ({ ...prev, [provider.id]: e.target.value }))}
                  onKeyDown={e => { if (e.key === 'Enter') handleSave(provider.id) }}
                  placeholder={provider.placeholder}
                  style={{
                    flex: 1, minWidth: 0, padding: '4px 7px',
                    fontSize: 10, fontFamily: 'monospace',
                    background: inputBg, color: t.text, outline: 'none',
                    border: `1px solid ${connected[provider.id] ? '#22c55e44' : panelBorder}`,
                    borderRadius: 4,
                    transition: 'border-color 0.15s',
                  }}
                  onFocus={e => e.target.style.borderColor = t.accent}
                  onBlur={e => e.target.style.borderColor = connected[provider.id] ? '#22c55e44' : panelBorder}
                />
                <button
                  onClick={() => handleSave(provider.id)}
                  disabled={!apiKeys[provider.id]}
                  style={{
                    padding: '4px 9px', fontSize: 10, fontWeight: 500,
                    borderRadius: 4, flexShrink: 0, transition: 'all 0.15s',
                    cursor: apiKeys[provider.id] ? 'pointer' : 'not-allowed',
                    border: `1px solid ${
                      savedKeys[provider.id] ? '#22c55e'
                      : apiKeys[provider.id] ? t.accent
                      : panelBorder
                    }`,
                    background: savedKeys[provider.id]
                      ? '#22c55e22'
                      : apiKeys[provider.id] ? t.accentBg : inputBg,
                    color: savedKeys[provider.id]
                      ? '#22c55e'
                      : apiKeys[provider.id] ? t.accentFg : mutedText,
                  }}
                >
                  {savedKeys[provider.id]
                    ? '✓'
                    : connected[provider.id] ? 'Update' : 'Save'}
                </button>
              </div>
            </div>
          ))}

          {/* Footer */}
          <div
            className="px-3 py-2 flex items-center justify-between"
            style={{ background: dark ? '#0a0d11' : '#fafafa' }}
          >
            <span style={{ fontSize: 9, color: mutedText }}>
              🔒 Stored locally in your browser
            </span>
            <span style={{ fontSize: 9, color: mutedText }}>
              Claude · GPT-4o · Gemini
            </span>
          </div>
        </div>
      )}
    </div>
  )
}