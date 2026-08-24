import { useContext, useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ThemeContext } from '../App'
import { getStyles } from './Login'
import {
  getAdminApiKeysStatus,
  getAdminLogs,
  getAdminUsers,
  patchAdminUser,
} from '../api/client'
import { useAdminAuth } from '../hooks/useAdminAuth'

const getDashboardStyles = (theme) => {
  const dark = theme === 'dark'
  return `
    .admin-shell {
      width: min(1200px, calc(100vw - 40px));
      margin: 84px auto 30px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .admin-top-row {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }

    .admin-stat {
      border: 1px solid ${dark ? '#242424' : '#eee7dc'};
      border-radius: 12px;
      padding: 12px;
      background: ${dark ? '#121212' : '#fcfbf8'};
    }

    .admin-stat-label {
      margin: 0;
      font-family: 'JetBrains Mono', monospace;
      color: ${dark ? '#9ca3af' : '#6b7280'};
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .admin-stat-value {
      margin: 7px 0 0;
      font-size: 28px;
      font-weight: 700;
      color: ${dark ? '#f9fafb' : '#111827'};
      letter-spacing: -0.03em;
    }

    .admin-controls {
      border: 1px solid ${dark ? '#242424' : '#eee7dc'};
      border-radius: 12px;
      background: ${dark ? '#121212' : '#fcfbf8'};
      padding: 12px;
      display: grid;
      grid-template-columns: 1.4fr repeat(2, minmax(0, 0.7fr)) auto auto;
      gap: 8px;
    }

    .admin-input,
    .admin-select {
      width: 100%;
      border: 1px solid ${dark ? '#2a2a2a' : '#ddd8cc'};
      background: ${dark ? '#0f0f0f' : '#ffffff'};
      color: ${dark ? '#f3f4f6' : '#1f2937'};
      border-radius: 10px;
      padding: 10px 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      outline: none;
    }

    .admin-input:focus,
    .admin-select:focus {
      border-color: #eab308;
      box-shadow: 0 0 0 3px rgba(234,179,8,0.18);
    }

    .admin-btn {
      border: none;
      border-radius: 10px;
      padding: 10px 12px;
      background: #eab308;
      color: #0a0a0a;
      font-family: 'Syne', sans-serif;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.2s;
    }

    .admin-btn:hover {
      background: #f0c020;
    }

    .admin-btn.ghost {
      background: ${dark ? '#1f2937' : '#e8e3d8'};
      color: ${dark ? '#e5e7eb' : '#374151'};
    }

    .admin-table-wrap {
      border: 1px solid ${dark ? '#242424' : '#eee7dc'};
      border-radius: 12px;
      background: ${dark ? '#121212' : '#fcfbf8'};
      overflow: auto;
    }

    .admin-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: ${dark ? '#d1d5db' : '#374151'};
    }

    .admin-table th,
    .admin-table td {
      text-align: left;
      padding: 10px;
      border-bottom: 1px solid ${dark ? '#1d1d1d' : '#eee7dc'};
      vertical-align: top;
    }

    .admin-table th {
      text-transform: uppercase;
      font-size: 10px;
      letter-spacing: 0.05em;
      color: ${dark ? '#9ca3af' : '#6b7280'};
    }

    .chip {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 10px;
      font-weight: 700;
    }

    .chip.ok { background: rgba(34,197,94,0.15); color: #16a34a; }
    .chip.warn { background: rgba(245,158,11,0.17); color: #d97706; }
    .chip.fail { background: rgba(239,68,68,0.17); color: #dc2626; }

    .admin-side {
      border: 1px solid ${dark ? '#242424' : '#eee7dc'};
      border-radius: 12px;
      background: ${dark ? '#121212' : '#fcfbf8'};
      padding: 12px;
    }

    .admin-side h3 {
      margin: 0 0 10px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: ${dark ? '#9ca3af' : '#6b7280'};
      font-family: 'JetBrains Mono', monospace;
    }

    .admin-log-list {
      display: flex;
      flex-direction: column;
      gap: 7px;
      max-height: 260px;
      overflow: auto;
    }

    .admin-log-item {
      border: 1px solid ${dark ? '#202020' : '#ede6d8'};
      border-radius: 8px;
      padding: 8px;
      font-size: 10px;
      line-height: 1.5;
      color: ${dark ? '#d1d5db' : '#374151'};
      background: ${dark ? '#0e0e0e' : '#fffdf8'};
      font-family: 'JetBrains Mono', monospace;
      word-break: break-word;
    }

    .layout-split {
      display: grid;
      grid-template-columns: 1fr 330px;
      gap: 12px;
    }

    .inline-actions {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .mini-btn {
      border: 1px solid ${dark ? '#374151' : '#d1d5db'};
      background: transparent;
      color: ${dark ? '#e5e7eb' : '#374151'};
      border-radius: 7px;
      padding: 4px 8px;
      cursor: pointer;
      font-size: 10px;
      font-family: 'JetBrains Mono', monospace;
    }

    .mini-btn:hover {
      border-color: #eab308;
      color: #eab308;
    }

    .admin-error {
      margin: 0;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: #ef4444;
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.28);
      border-radius: 8px;
      padding: 8px 10px;
    }

    @media (max-width: 1080px) {
      .layout-split { grid-template-columns: 1fr; }
    }

    @media (max-width: 860px) {
      .admin-top-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .admin-controls { grid-template-columns: 1fr; }
    }
  `
}

const fmt = (value) => {
  if (!value) return 'n/a'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return 'n/a'
  return dt.toLocaleString()
}

const statusChipClass = (status) => {
  if (status === 'added') return 'chip ok'
  if (status === 'invalid') return 'chip fail'
  return 'chip warn'
}

export default function AdminDashboard() {
  const { theme, toggleTheme } = useContext(ThemeContext)
  const { loading, isAdminAuthenticated, adminUser, logout } = useAdminAuth()

  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [summary, setSummary] = useState({ total_users: 0, active_users: 0, missing_api_keys: 0, invalid_api_keys: 0 })
  const [users, setUsers] = useState([])
  const [logs, setLogs] = useState([])
  const [keyOverview, setKeyOverview] = useState([])

  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [keyFilter, setKeyFilter] = useState('all')

  const styleSheet = useMemo(() => getStyles(theme) + getDashboardStyles(theme), [theme])

  const fetchData = async () => {
    try {
      setBusy(true)
      setError('')
      const [usersRes, logsRes, keysRes] = await Promise.all([
        getAdminUsers({ search, role: roleFilter, key_status: keyFilter }),
        getAdminLogs(),
        getAdminApiKeysStatus(),
      ])
      setSummary(usersRes?.summary || {})
      setUsers(usersRes?.users || [])
      setLogs(logsRes?.requests || [])
      setKeyOverview(keysRes?.items || [])
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load admin dashboard')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!loading && isAdminAuthenticated) {
      fetchData()
    }
  }, [loading, isAdminAuthenticated])

  const onApplyFilters = (event) => {
    event.preventDefault()
    fetchData()
  }

  const disableUser = async (userId, disabled) => {
    try {
      await patchAdminUser(userId, { is_disabled: !disabled })
      await fetchData()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to update user status')
    }
  }

  const resetApiKeyStatus = async (userId) => {
    if (!window.confirm('Reset API keys for this user? This will clear stored key records.')) return
    try {
      await patchAdminUser(userId, { reset_api_key_status: true })
      await fetchData()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to reset API key status')
    }
  }

  if (!loading && !isAdminAuthenticated) {
    return <Navigate to="/admin/login" replace />
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
            <span className="nav-logo-name">PRGuard Admin</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === 'dark' ? '☀' : '◑'}
            </button>
            <button className="admin-btn ghost" onClick={logout}>Sign out</button>
          </div>
        </nav>

        <div className="admin-shell">
          <div className="rag-badge">
            <span className="rag-badge-dot" />
            Signed in as {adminUser?.username || 'admin'}
          </div>

          {error ? <p className="admin-error">{error}</p> : null}

          <div className="admin-top-row">
            <div className="admin-stat"><p className="admin-stat-label">Total users</p><p className="admin-stat-value">{summary.total_users || 0}</p></div>
            <div className="admin-stat"><p className="admin-stat-label">Active users</p><p className="admin-stat-value">{summary.active_users || 0}</p></div>
            <div className="admin-stat"><p className="admin-stat-label">Missing API keys</p><p className="admin-stat-value">{summary.missing_api_keys || 0}</p></div>
            <div className="admin-stat"><p className="admin-stat-label">Invalid API keys</p><p className="admin-stat-value">{summary.invalid_api_keys || 0}</p></div>
          </div>

          <form className="admin-controls" onSubmit={onApplyFilters}>
            <input className="admin-input" placeholder="Search username or email" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select className="admin-select" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
              <option value="all">All roles</option>
              <option value="admin">Admin</option>
              <option value="user">User</option>
            </select>
            <select className="admin-select" value={keyFilter} onChange={(e) => setKeyFilter(e.target.value)}>
              <option value="all">All key states</option>
              <option value="added">Added</option>
              <option value="missing">Missing</option>
              <option value="invalid">Invalid</option>
            </select>
            <button type="submit" className="admin-btn">Apply</button>
            <button type="button" className="admin-btn ghost" onClick={fetchData}>Refresh</button>
          </form>

          <div className="layout-split">
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>API Key Status</th>
                    <th>API Key</th>
                    <th>Created Date</th>
                    <th>Last Login</th>
                    <th>Usage Errors</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.username}</td>
                      <td>{u.email || 'n/a'}</td>
                      <td>{u.role}</td>
                      <td><span className={statusChipClass(u.api_key_status)}>{u.api_key_status}</span></td>
                      <td><code style={{ fontSize: '10px', wordBreak: 'break-all', fontFamily: '"JetBrains Mono", monospace' }}>{u.api_key_full || 'none'}</code></td>
                      <td>{fmt(u.created_at)}</td>
                      <td>{fmt(u.last_login)}</td>
                      <td>{u.api_key_usage_errors || 0}</td>
                      <td>
                        <div className="inline-actions">
                          <button className="mini-btn" onClick={() => disableUser(u.id, u.is_disabled)}>
                            {u.is_disabled ? 'Enable' : 'Disable'}
                          </button>
                          <button className="mini-btn" onClick={() => resetApiKeyStatus(u.id)}>
                            Reset key state
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!busy && users.length === 0 ? (
                    <tr>
                      <td colSpan="9">No users match current filters.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            <aside className="admin-side">
              <h3>Recent API usage errors</h3>
              <div className="admin-log-list">
                {logs.filter((item) => item.status === 'failure').slice(0, 12).map((item, idx) => (
                  <div className="admin-log-item" key={`${item.timestamp}-${idx}`}>
                    <div><strong>{item.username || 'unknown'}</strong> on {item.repo || 'n/a'}</div>
                    <div>{item.error || 'Unknown failure'}</div>
                    <div>{fmt(item.timestamp)}</div>
                  </div>
                ))}
                {logs.filter((item) => item.status === 'failure').length === 0 ? (
                  <div className="admin-log-item">No API key usage failures recorded.</div>
                ) : null}
              </div>

              <h3 style={{ marginTop: 14 }}>Key health snapshot</h3>
              <div className="admin-log-list">
                {keyOverview.slice(0, 12).map((item, idx) => (
                  <div className="admin-log-item" key={`${item.user_id}-${idx}`}>
                    <div><strong>{item.username}</strong> ({item.provider || 'n/a'})</div>
                    <div>Status: {item.status}</div>
                    <div>Validation: {item.validation_result}</div>
                  </div>
                ))}
              </div>
            </aside>
          </div>
        </div>
      </div>
    </>
  )
}
