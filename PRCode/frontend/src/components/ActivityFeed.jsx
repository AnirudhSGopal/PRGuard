import { useContext, useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { ThemeContext } from '../App'
import { getTheme, getLabelColors, truncate, timeAgo } from '../utils/helpers'
import { sendMessage, toggleWorkingOn } from '../api/client'

function Toast({ message, type, onClose, t }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  const bgColor = type === 'error' ? '#ef4444' : (type === 'success' ? '#22c55e' : t.accent)

  return (
    <div style={{
      position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
      padding: '10px 16px', borderRadius: 8, background: bgColor, color: '#fff',
      fontSize: 12, fontWeight: 500, boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      zIndex: 10000, display: 'flex', alignItems: 'center', gap: 8,
      animation: 'slideUp 0.3s ease-out'
    }}>
      <span>{message}</span>
    </div>
  )
}

function IssueMenu({ issue, setIssues, selectedRepo, t, theme, onClose, buttonRef, addToast }) {
  const [generating, setGenerating] = useState(false)
  const [workingOnLoading, setWorkingOnLoading] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const ref = useRef(null)

  useEffect(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect()
      const menuHeight = 220 // Approximate height with 4 items
      const showAbove = rect.top > menuHeight
      setPos({
        top: showAbove ? rect.top - menuHeight - 4 : rect.bottom + 4,
        left: rect.right - 240,
      })
    }
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target) &&
          buttonRef.current && !buttonRef.current.contains(e.target)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose, buttonRef])

  const generateReport = async () => {
    if (generating) return
    setGenerating(true)
    try {
      const prompt = `Generate a full report for issue #${issue.number}: ${issue.title}. Include: 1) Issue summary 2) RAG codebase context 3) Root cause analysis 4) Step by step fix guide`
      const res = await sendMessage(prompt, selectedRepo, issue.number)
      const report = res.message || res.answer
      await navigator.clipboard.writeText(report)
      addToast("✅ Report copied to clipboard", "success")
      onClose()
    } catch (err) {
      addToast("❌ Something went wrong, try again", "error")
    } finally {
      setGenerating(false)
    }
  }

  const copyIssueLink = async () => {
    try {
      const [owner, repoName] = selectedRepo.split('/')
      const url = `https://github.com/${owner}/${repoName}/issues/${issue.number}`
      await navigator.clipboard.writeText(url)
      addToast("✅ Issue link copied", "success")
      onClose()
    } catch (err) {
      addToast("❌ Something went wrong, try again", "error")
    }
  }

  const exportForChatGPT = async () => {
    try {
      const [owner, repo] = selectedRepo.split('/')
      const labels = (issue.labels || []).join(', ')
      const prompt = `I need help fixing a GitHub issue. Here are the details:

Repository: ${owner}/${repo}
Issue #${issue.number}: ${issue.title}
Labels: ${labels}

Description:
${issue.body || 'No description provided.'}

Please help me:
1. Understand the root cause
2. Suggest a fix with code examples  
3. List files I likely need to change`

      await navigator.clipboard.writeText(prompt)
      addToast("✅ Exported! Paste it into ChatGPT", "success")
      onClose()
    } catch (err) {
      addToast("❌ Something went wrong, try again", "error")
    }
  }

  const handleMarkWorkingOn = async () => {
    if (workingOnLoading) return
    const nextState = !issue.working_on
    setWorkingOnLoading(true)
    
    // Optimistic update
    setIssues(prev => prev.map(is => is.id === issue.id ? { ...is, working_on: nextState } : is))

    try {
      await toggleWorkingOn(issue.number, selectedRepo, nextState)
      if (nextState) {
        addToast(`✅ Tracking issue #${issue.number}`, "success")
      } else {
        addToast("Removed from working on", "success")
      }
      onClose()
    } catch (err) {
      // Revert optimistic update
      setIssues(prev => prev.map(is => is.id === issue.id ? { ...is, working_on: !nextState } : is))
      addToast("❌ Something went wrong, try again", "error")
    } finally {
      setWorkingOnLoading(false)
    }
  }

  const menuItems = [
    { label: 'Generate & Copy Report', icon: '⎘', action: generateReport, desc: 'Full issue + RAG context + fix guide', loading: generating },
    { label: 'Copy Issue Link', icon: '🔗', action: copyIssueLink, desc: 'GitHub issue URL' },
    { label: 'Export for ChatGPT', icon: '↗', action: exportForChatGPT, desc: 'Prompt ready to paste' },
    { 
      label: issue.working_on ? 'Remove from Working On' : 'Mark as Working On', 
      icon: '◎', 
      action: handleMarkWorkingOn, 
      desc: 'Track this issue for yourself',
      loading: workingOnLoading,
      color: issue.working_on ? '#f59e0b' : t.accent
    },
  ]

  const menuContent = (
    <div ref={ref} style={{ position: 'fixed', top: `${pos.top}px`, left: `${pos.left}px`, zIndex: 9999, background: t.bg2, border: `1px solid ${t.border}`, borderRadius: 8, padding: '4px 0', width: 240, boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
      {menuItems.map((item, i) => (
        <div key={i}>
          {i === menuItems.length - 1 && <div style={{ borderTop: `1px solid ${t.border}`, margin: '4px 0' }}/>}
          <button onClick={(e) => { e.stopPropagation(); item.action() }}
            disabled={item.loading}
            style={{ width: '100%', textAlign: 'left', padding: '10px 12px', display: 'flex', alignItems: 'flex-start', gap: 10, background: 'transparent', border: 'none', cursor: item.loading ? 'default' : 'pointer', transition: 'background 0.15s', opacity: item.loading ? 0.7 : 1 }}
            onMouseEnter={e => { if (!item.loading) e.currentTarget.style.background = t.bg3 }}
            onMouseLeave={e => { if (!item.loading) e.currentTarget.style.background = 'transparent' }}>
            <span style={{ fontSize: 14, color: item.color || t.accentText, flexShrink: 0, marginTop: 1 }}>
              {item.loading ? '⏳' : item.icon}
            </span>
            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: t.text }}>{item.label}</div>
              <div style={{ fontSize: 10, color: t.text3, marginTop: 2 }}>{item.desc}</div>
            </div>
          </button>
        </div>
      ))}
    </div>
  )

  return createPortal(menuContent, document.body)
}

export default function IssueList({ issues, setIssues, selectedRepo, selectedIssue, onSelectIssue, loading }) {
  const { theme } = useContext(ThemeContext)
  const t = getTheme(theme)
  const [openMenuId, setOpenMenuId] = useState(null)
  const [toasts, setToasts] = useState([])
  const buttonRefs = useRef({})

  const addToast = useCallback((message, type) => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  if (loading) return (
    <div style={{ padding: 8 }}>
      {[1, 2, 3].map(i => (
        <div key={i} style={{ height: 80, borderRadius: 6, background: t.bg3, marginBottom: 8, animation: 'pulse 1.5s infinite' }}/>
      ))}
    </div>
  )

  return (
    <div style={{ position: 'relative' }}>
      {issues.map(issue => {
        const isActive = selectedIssue?.id === issue.id
        const menuOpen = openMenuId === issue.id

        if (!buttonRefs.current[issue.id]) {
          buttonRefs.current[issue.id] = { current: null }
        }

        return (
          <div key={issue.id} style={{ borderLeft: `2px solid ${isActive ? t.accent : 'transparent'}`, background: isActive ? (theme === 'dark' ? '#1a2030' : '#fef3c7') : 'transparent', borderBottom: `1px solid ${t.border}`, position: 'relative', transition: 'all 0.15s' }}>
            <div
              onClick={() => onSelectIssue(issue)}
              style={{ padding: '14px 36px 14px 12px', cursor: 'pointer' }}
              onMouseEnter={e => { if (!isActive) e.currentTarget.parentElement.style.background = t.bg3 }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.parentElement.style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <div style={{ fontSize: 10, color: t.accentText, fontFamily: 'monospace' }}>#{issue.number}</div>
                {issue.working_on && (
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#f59e0b', boxShadow: '0 0 8px #f59e0b99' }} title="Working on this issue"/>
                )}
              </div>
              <div style={{ fontSize: 12, color: t.text2, lineHeight: 1.5, marginBottom: 10 }}>{truncate(issue.title, 44)}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                {(issue.labels || []).map(label => (
                  <span key={label} className={`text-[9px] px-1.5 py-0.5 rounded border ${getLabelColors(theme, label)}`}>{label}</span>
                ))}
                <span style={{ fontSize: 10, color: t.text3, marginLeft: 'auto' }}>{timeAgo(issue.created_at)}</span>
              </div>
            </div>

            <button
              ref={el => buttonRefs.current[issue.id] = { current: el }}
              onClick={(e) => { e.stopPropagation(); setOpenMenuId(menuOpen ? null : issue.id) }}
              style={{ position: 'absolute', top: 14, right: 10, width: 24, height: 24, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: menuOpen ? t.accentText : t.text3, background: menuOpen ? t.bg3 : 'transparent', border: `1px solid ${menuOpen ? t.border : 'transparent'}`, transition: 'all 0.15s' }}
              title="Issue options">
              <span style={{ fontSize: 13, letterSpacing: 1, lineHeight: 1 }}>···</span>
            </button>

            {menuOpen && (
              <IssueMenu 
                issue={issue} 
                setIssues={setIssues}
                selectedRepo={selectedRepo}
                t={t} 
                theme={theme} 
                onClose={() => setOpenMenuId(null)} 
                buttonRef={buttonRefs.current[issue.id]}
                addToast={addToast}
              />
            )}
          </div>
        )
      })}

      {toasts.map(toast => (
        <Toast key={toast.id} {...toast} onClose={() => removeToast(toast.id)} t={t} />
      ))}

      <style>{`
        @keyframes slideUp {
          from { transform: translate(-50%, 20px); opacity: 0; }
          to { transform: translate(-50%, 0); opacity: 1; }
        }
        @keyframes pulse {
          0% { opacity: 0.4; }
          50% { opacity: 0.8; }
          100% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}