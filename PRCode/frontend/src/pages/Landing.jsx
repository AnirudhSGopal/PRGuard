import { useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { ThemeContext } from '../App'
import { getTheme } from '../utils/helpers'

export default function Landing() {
  const { theme, toggleTheme } = useContext(ThemeContext)
  const t = getTheme(theme)
  const navigate = useNavigate()

  const features = [
    { title: 'RAG Codebase Indexing', desc: 'Entire repo indexed semantically. Ask anything, get answers grounded in real code.' },
    { title: 'GitHub Issues Linked', desc: 'Issues automatically linked to the files and functions responsible.' },
    { title: 'Contribution Roadmap', desc: 'Step-by-step guide on exactly how to fix each issue.' },
    { title: 'Claude Sonnet Powered', desc: 'Best-in-class code understanding with context-aware explanations.' },
    { title: 'Smart Chunking', desc: 'Function-level chunking with metadata for precise retrieval.' },
    { title: 'LangSmith Observability', desc: 'Every query traced, scored, and measured for quality.' },
  ]

  return (
    <div className="min-h-screen" style={{ background: t.bg, color: t.text }}>
      <nav
        className="px-6 h-10 flex items-center justify-between"
        style={{ borderBottom: `1px solid ${t.border}`, background: t.bg2 }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div
            className="w-6 h-6 rounded text-[10px] font-bold flex items-center justify-center"
            style={{ background: t.accentBg, color: t.accentFg }}
          >
            PG
          </div>
          <span className="font-bold text-sm" style={{ color: t.text }}>
            PR<span style={{ color: t.accentText }}>Guard</span>
          </span>
        </div>

        {/* Right: theme toggle + CTA */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            aria-label="Toggle theme"
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: t.bg3,
              border: `1px solid ${t.border}`,
              color: t.text2,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 13,
              flexShrink: 0,
            }}
          >
            {theme === 'dark' ? '☀' : '◑'}
          </button>

          <button
            onClick={() => navigate('/login')}
            className="text-xs px-3 py-1.5 rounded font-bold"
            style={{ background: t.accentBg, color: t.accentFg }}
          >
            Open Dashboard →
          </button>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-20 text-center">
        <div
          className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-full mb-8"
          style={{ background: t.bg3, border: `1px solid ${t.border}`, color: t.accentText }}
        >
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          Open Source Codebase Learning Assistant
        </div>

        <h1 className="text-4xl font-bold mb-4 leading-tight" style={{ color: t.text }}>
          Understand any codebase.<br />
          <span style={{ color: t.accentText }}>Contribute with confidence.</span>
        </h1>

        <p className="text-base mb-10 max-w-xl mx-auto leading-relaxed" style={{ color: t.text2 }}>
          Connect a GitHub repo. PRGuard indexes the entire codebase, links open issues to responsible code,
          and answers your questions so you can contribute without getting lost.
        </p>

        <div className="flex items-center justify-center gap-3 flex-wrap">
          <button
            onClick={() => navigate('/login')}
            className="px-8 py-3.5 rounded-lg font-bold text-sm"
            style={{ background: t.accentBg, color: t.accentFg }}
          >
            User Login →
          </button>
          <button
            onClick={() => navigate('/admin/login')}
            className="px-6 py-3.5 rounded-lg font-bold text-sm"
            style={{ background: t.bg3, color: t.text2, border: `1px solid ${t.border}` }}
          >
            Admin Login
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-16 text-left">
          {features.map(f => (
            <div
              key={f.title}
              className="rounded-lg p-4"
              style={{ background: t.bg3, border: `1px solid ${t.border}` }}
            >
              <h3
                className="text-xs font-bold uppercase tracking-widest mb-2"
                style={{ color: t.accentText }}
              >
                {f.title}
              </h3>
              <p className="text-xs leading-relaxed" style={{ color: t.text2 }}>
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}