import { useContext } from 'react'
import { ThemeContext } from '../App'
import { getTheme } from '../utils/helpers'
import { useAuth } from '../hooks/useAuth'

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/>
      <line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  )
}

export default function Navbar() {
  const { theme, setTheme } = useContext(ThemeContext)
  const { user, logout }    = useAuth()
  const t = getTheme(theme)

  return (
    <nav
      style={{ background: t.bg2, borderBottom: `1px solid ${t.border}` }}
      className="h-10 flex items-center justify-between px-4 flex-shrink-0"
    >
      {/* Left — logo */}
      <div className="flex items-center gap-2">
        <div
          style={{ background: t.accentBg, color: t.accentFg }}
          className="w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold"
        >
          PG
        </div>
        <span className="font-bold text-sm" style={{ color: t.text }}>
          PR<span style={{ color: t.accentText }}>Guard</span>
        </span>
        <span className="text-xs ml-2" style={{ color: t.text3 }}>
          Codebase Learning Assistant
        </span>
      </div>

      {/* Right — controls */}
      <div className="flex items-center gap-3">
        <div
          className="flex items-center gap-1.5 text-xs px-3 py-1 rounded-full"
          style={{ color: t.text3, border: `1px solid ${t.border}` }}
        >
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"/>
          RAG Active
        </div>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className="flex items-center justify-center w-8 h-8 rounded-lg transition-all"
          style={{
            border:     `1px solid ${t.border}`,
            background: t.bg3,
            color:      theme === 'dark' ? '#f59e0b' : '#6366f1',
          }}
        >
          {theme === 'dark' ? <SunIcon/> : <MoonIcon/>}
        </button>

        {/* User avatar & Logout */}
        {user && (
          <div className="flex items-center gap-2">
            {user.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.login}
                style={{
                  width: 25, height: 25,
                  borderRadius: '50%',
                  border: `1px solid ${t.border}`,
                  objectFit: 'cover',
                }}
              />
            ) : (
              <div
                className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
                style={{ background: t.bg3, color: t.accentText, border: `1px solid ${t.border}` }}
              >
                {user.login?.[0]?.toUpperCase() || 'A'}
              </div>
            )}

            <button
              onClick={logout}
              className="text-[10px] uppercase tracking-wider font-semibold opacity-60 hover:opacity-100 transition-opacity"
              style={{ color: t.text3, marginLeft: 2 }}
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </nav>
  )
}