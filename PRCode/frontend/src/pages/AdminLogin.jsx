import { useContext, useMemo, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ThemeContext } from '../App'
import { getStyles } from './Login'
import { adminLogin } from '../api/client'
import { useSession } from '../hooks/useSession'

const getAdminLoginStyles = (theme) => {
  const dark = theme === 'dark'
  return `
    .admin-form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 14px;
    }

    .admin-input {
      width: 100%;
      border: 1px solid ${dark ? '#2a2a2a' : '#ddd8cc'};
      background: ${dark ? '#0f0f0f' : '#fcfbf8'};
      color: ${dark ? '#f3f4f6' : '#1f2937'};
      border-radius: 10px;
      padding: 11px 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      outline: none;
    }

    .admin-input:focus {
      border-color: #eab308;
      box-shadow: 0 0 0 3px rgba(234,179,8,0.18);
    }

    .admin-input::placeholder {
      color: ${dark ? '#6b7280' : '#9ca3af'};
    }

    .admin-error {
      margin: 0 0 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: #ef4444;
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.28);
      border-radius: 8px;
      padding: 8px 10px;
    }
  `
}

export default function AdminLogin() {
  const { theme, toggleTheme } = useContext(ThemeContext)
  const navigate = useNavigate()
  const { loading, isAdmin } = useSession()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const styleSheet = useMemo(() => getStyles(theme) + getAdminLoginStyles(theme), [theme])

  if (!loading && isAdmin) {
    return <Navigate to="/admin/dashboard" replace />
  }

  const onSubmit = async (event) => {
    event.preventDefault()
    if (!email.trim() || !password) {
      setError('Email and password are required.')
      return
    }

    try {
      setBusy(true)
      setError('')
      const data = await adminLogin(email.trim(), password)
      navigate(data?.role === 'admin' ? '/admin/dashboard' : '/dashboard', { replace: true })
    } catch (err) {
      const message = err?.response?.data?.detail || 'Admin sign-in failed.'
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <style>{styleSheet}</style>
      <div className="auth-root">
        <div className="auth-grid" />
        <div className="auth-glow" />
        <div className="auth-glow-2" />

        <nav className="auth-navbar">
          <div className="nav-logo">
            <div className="nav-logo-icon">PG</div>
            <span className="nav-logo-name">PRGuard</span>
          </div>
          <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle theme">
            {theme === 'dark' ? '☀' : '◑'}
          </button>
        </nav>

        <div className="auth-card visible">
          <div className="auth-logo">
            <div className="auth-logo-icon">PG</div>
            <span className="auth-logo-name">PRGuard</span>
          </div>

          <div className="rag-badge">
            <span className="rag-badge-dot" />
            Admin authentication
          </div>

          <h1 className="auth-heading">
            Admin command center.<br />
            <span className="accent">Restricted access only.</span>
          </h1>

          <p className="auth-sub">
            Sign in with your admin email and password to manage users, roles, and API key health.
          </p>

          {error ? <p className="admin-error">{error}</p> : null}

          <form className="admin-form" onSubmit={onSubmit}>
            <input
              className="admin-input"
              placeholder="Admin email or username"
              type="text"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={busy}
            />
            <input
              className="admin-input"
              placeholder="Admin password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
            />
            <button type="submit" className="github-btn" disabled={busy}>
              {busy ? 'Signing in...' : 'Sign in as admin'}
            </button>
          </form>
        </div>
      </div>
    </>
  )
}
