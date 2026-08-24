import { useContext, useState, useEffect, useRef } from 'react'
import { ThemeContext } from '../App'
import { getTheme } from '../utils/helpers'
import { sendMessage as apiSendMessage, getScopedProvider, setScopedProvider } from '../api/client'
import { useApiKeyGuard } from '../hooks/useApiKeyGuard'
import { useRepos } from '../hooks/useReviews'
// ── Model options ─────────────────────────────────────────────────────────────
const MODELS = [
  { id: 'claude', label: 'Claude Sonnet 4', sub: 'Anthropic · Best for code' },
  { id: 'gpt',    label: 'GPT-4o',          sub: 'OpenAI · Most popular' },
  { id: 'gemini', label: 'Gemini 1.5 Pro',  sub: 'Google · Fast & Smart' },
]

const SUGGESTED = [
  'How does the auth module work?',
  'Which files do I need to change?',
  'Explain the folder structure',
  'How do I run the tests?',
]

const SYSTEM_PROMPT = (repo, issue, model) =>
  `You are PRGuard AI, a codebase learning assistant.
Repository: ${repo}${issue ? `\nFocused issue: #${issue.number} — "${issue.title}"` : ''}
Model: ${model}
Help developers understand codebases, fix issues, and contribute. Be concise and technical. Use markdown code blocks.`

// ── Content type detector ─────────────────────────────────────────────────────
function healJson(str) {
  let s = str.trim()
  if (!s.startsWith('{')) return null
  const lastQuote = s.lastIndexOf('"')
  const lastOpenBrace = s.lastIndexOf('{')
  const lastColon = s.lastIndexOf(':')
  if (lastQuote > lastOpenBrace && lastQuote > lastColon) {
    const quoteCount = (s.match(/"/g) || []).length
    if (quoteCount % 2 !== 0) s += '"'
  }
  const openBraces = (s.match(/\{/g) || []).length
  const closeBraces = (s.match(/\}/g) || []).length
  for (let i = 0; i < (openBraces - closeBraces); i++) s += '}'
  return s
}

function detectContentType(content) {
  if (!content) return 'text'
  const trimmed = content.trim()

  // 1. Check for images
  if (/^https?:\/\/.+\.(png|jpg|jpeg|gif|webp|svg)(\?.*)?$/i.test(trimmed)) return 'image'
  if (/!\[.*?\]\(https?:\/\/.+\.(png|jpg|jpeg|gif|webp|svg)(\?.*)?\)/i.test(trimmed)) return 'image_md'

  // 2. Check for JSON (even inside markdown code blocks)
  const jsonMatch = trimmed.match(/```(?:json)?\s*(\{[\s\S]*\})\s*```/) || trimmed.match(/^(\{[\s\S]*\})$/)
  const target = jsonMatch ? jsonMatch[1] : trimmed
  
  if (target.startsWith('{')) {
    try {
      const g = JSON.parse(target)
      if (g.type === 'issue_analysis') return 'issue_viz'
      if (g.type === 'chart' || (g.labels && g.values)) return 'chart'
      return 'json'
    } catch { 
      const healed = healJson(target)
      if (healed) {
        try {
          const g = JSON.parse(healed)
          if (g.type === 'issue_analysis' || g.labels) return 'issue_viz'
        } catch { /* still fail */ }
      }
    }
  }

  return 'text'
}

// ── Inline bar chart ──────────────────────────────────────────────────────────
function ChartBubble({ data, t, dark }) {
  const { labels = [], values = [], title = '' } = data
  const max = Math.max(...values, 1)
  const barColors = ['#7F77DD', '#1D9E75', '#D85A30', '#378ADD', '#BA7517', '#D4537E']
  const chartH = 120
  const barW = Math.min(56, Math.floor(460 / Math.max(labels.length, 1)) - 10)

  return (
    <div style={{ background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 12, padding: '14px 16px', maxWidth: '88%' }}>
      {title && <div style={{ fontSize: 10, fontWeight: 600, color: t.text2, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{title}</div>}
      <svg width="100%" viewBox={`0 0 ${Math.max(labels.length * (barW + 12) + 40, 280)} ${chartH + 46}`} style={{ overflow: 'visible' }}>
        {values.map((v, i) => {
          const barH = Math.max(4, (v / max) * chartH)
          const x = 20 + i * (barW + 12)
          const y = chartH - barH
          const color = barColors[i % barColors.length]
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={barH} rx="4" fill={color} opacity="0.85" />
              <text x={x + barW / 2} y={y - 5} textAnchor="middle" fontSize="11" fill={t.text2} fontFamily="monospace">{v}</text>
              <text x={x + barW / 2} y={chartH + 16} textAnchor="middle" fontSize="10" fill={t.text3}>
                {(labels[i] || '').length > 8 ? labels[i].slice(0, 7) + '…' : labels[i]}
              </text>
            </g>
          )
        })}
        <line x1="16" y1={chartH} x2={Math.max(labels.length * (barW + 12) + 30, 270)} y2={chartH} stroke={t.border} strokeWidth="0.5" />
      </svg>
    </div>
  )
}

// ── Issue visualization card ──────────────────────────────────────────────────
function IssueVizBubble({ data, t, dark, onFollowUp }) {
  const severityColor = { High: '#E24B4A', Medium: '#BA7517', Low: '#1D9E75' }[data.severity] || '#888'
  const stepColors = ['#E24B4A', '#BA7517', '#BA7517', '#1D9E75', '#1D9E75']
  const barColors = ['#7F77DD', '#1D9E75', '#D85A30', '#378ADD', '#D4537E']
  const maxW = Math.max(...(data.files || []).map(f => f.weight || 0), 1)

  return (
    <div style={{ maxWidth: '96%', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 12, padding: '12px 14px' }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: severityColor + '22', color: severityColor, fontWeight: 600, border: `1px solid ${severityColor}44` }}>{data.severity} severity</span>
          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: dark ? '#1e2535' : '#f0f4ff', color: t.text2, border: `1px solid ${t.border}` }}>Est. {data.effort}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
          {[{ label: 'Root cause', value: data.root_cause }, { label: 'Fix summary', value: data.fix_summary }].map((m, i) => (
            <div key={i} style={{ background: dark ? '#0d0f12' : '#f8f8f8', borderRadius: 8, padding: '10px 12px', border: `1px solid ${t.border}` }}>
              <div style={{ fontSize: 9, color: t.text3, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{m.label}</div>
              <div style={{ fontSize: 12, color: t.text, lineHeight: 1.5 }}>{m.value}</div>
            </div>
          ))}
        </div>

        {data.files?.length > 0 && (
          <div>
            <div style={{ fontSize: 9, color: t.text3, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Files to change</div>
            {data.files.map((f, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: i < data.files.length - 1 ? `1px solid ${t.border}` : 'none' }}>
                <code style={{ fontSize: 10, color: t.accentText, minWidth: 160, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.path}</code>
                <div style={{ flex: 1, height: 5, background: dark ? '#1e2535' : '#e8e8e8', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', borderRadius: 3, background: barColors[i % barColors.length], width: `${(f.weight / maxW) * 100}%`, transition: 'width 0.6s ease' }} />
                </div>
                <span style={{ fontSize: 10, color: t.text3, minWidth: 70, textAlign: 'right' }}>{f.role}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {data.steps?.length > 0 && (
          <div style={{ background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 12, padding: '12px 14px' }}>
            <div style={{ fontSize: 9, color: t.text3, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Fix steps</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {data.steps.map((step, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <div style={{ width: 18, height: 18, borderRadius: '50%', background: stepColors[i] + '22', border: `1px solid ${stepColors[i]}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700, color: stepColors[i], flexShrink: 0, marginTop: 1 }}>{i + 1}</div>
                  <span style={{ fontSize: 11, color: t.text, lineHeight: 1.5 }}>{step}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {data.chart && (
          <div style={{ background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 12, padding: '12px 14px' }}>
            <div style={{ fontSize: 9, color: t.text3, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Issue breakdown</div>
            <ChartBubble data={data.chart} t={t} dark={dark} />
          </div>
        )}
      </div>

      {data.related?.length > 0 && (
        <div style={{ background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 12, padding: '12px 14px' }}>
          <div style={{ fontSize: 9, color: t.text3, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Related issues</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.related.map((r, i) => (
              <div key={i} style={{ padding: '8px 10px', background: dark ? '#0d0f12' : '#f8f8f8', borderRadius: 8, border: `1px solid ${t.border}` }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: t.text, marginBottom: 2 }}>#{r.number} · {r.title}</div>
                <div style={{ fontSize: 11, color: t.text3 }}>{r.note}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 6 }}>
        {[
          { label: 'Show code fix', prompt: 'Show me the exact code change needed for the files in the analysis' },
          { label: 'Write the test', prompt: 'Write a test for this fix' },
          { label: 'Scan for more', prompt: 'Are there other issues related to this in the codebase?' },
        ].map((btn, i) => (
          <button key={i} onClick={() => onFollowUp(btn.prompt)}
            style={{ flex: 1, padding: '7px 10px', fontSize: 11, fontWeight: 500, cursor: 'pointer', borderRadius: 7, background: dark ? '#1e2535' : '#f0f4ff', color: t.accentText, border: `1px solid ${t.border}`, transition: 'all 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = t.accent; e.currentTarget.style.background = t.accent + '20' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.background = dark ? '#1e2535' : '#f0f4ff' }}>
            {btn.label} →
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Image bubble ──────────────────────────────────────────────────────────────
function ImageBubble({ content, t, dark }) {
  const urlMatch = content.match(/https?:\/\/[^\s\)]+\.(png|jpg|jpeg|gif|webp|svg)(\?[^\s\)]*)?/i)
  const url = urlMatch ? urlMatch[0] : null
  const altMatch = content.match(/!\[(.*?)\]/)
  const alt = altMatch ? altMatch[1] : 'Image'
  if (!url) return <TextBubble content={content} t={t} dark={dark} isUser={false} />
  return (
    <div style={{ background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 12, overflow: 'hidden', maxWidth: '80%' }}>
      <img src={url} alt={alt} style={{ width: '100%', display: 'block', maxHeight: 400, objectFit: 'contain', background: dark ? '#0a0d11' : '#f5f5f5' }}
        onError={e => { e.target.style.display = 'none' }} />
      {alt && alt !== 'Image' && (
        <div style={{ padding: '6px 12px', fontSize: 11, color: t.text3, borderTop: `1px solid ${t.border}` }}>{alt}</div>
      )}
    </div>
  )
}

// ── Plain text bubble ─────────────────────────────────────────────────────────
function TextBubble({ content, t, dark, isUser }) {
  return (
    <div style={{ maxWidth: '80%', padding: '9px 13px', borderRadius: isUser ? '14px 4px 14px 14px' : '4px 14px 14px 14px', background: isUser ? (dark ? '#1e2535' : '#fef3c7') : (dark ? '#13161b' : '#fff'), border: `1px solid ${isUser ? (dark ? t.accent + '44' : '#d4860a44') : t.border}`, fontSize: 13, lineHeight: 1.65, color: t.text, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
      {content.split(/(```[\s\S]*?```)/g).map((part, i) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const code = part.slice(3, -3).replace(/^[a-z]+\n/, '')
          return <pre key={i} style={{ background: dark ? '#0a0d11' : '#f0f2f5', border: `1px solid ${t.border}`, borderRadius: 6, padding: '8px 10px', fontSize: 11, fontFamily: 'monospace', overflowX: 'auto', margin: '6px 0', color: t.text }}><code>{code}</code></pre>
        }
        return <span key={i}>{part}</span>
      })}
    </div>
  )
}

// ── Unified message bubble ────────────────────────────────────────────────────
function MessageBubble({ msg, t, dark, onFollowUp }) {
  const isUser = msg.role === 'user'
  const contentType = isUser ? 'text' : detectContentType(msg.content)

  let parsedData = null
  if (['issue_viz', 'chart'].includes(contentType)) {
    try {
      const trimmed = msg.content.trim()
      const jsonMatch = trimmed.match(/```(?:json)?\s*(\{[\s\S]*\})\s*```/) || trimmed.match(/^(\{[\s\S]*\})$/)
      const target = jsonMatch ? jsonMatch[1] : trimmed
      try {
        parsedData = JSON.parse(target)
      } catch {
        const healed = healJson(target)
        if (healed) parsedData = JSON.parse(healed)
      }
    } catch { /* fallback */ }
  }

  const renderContent = () => {
    if (isUser) return <TextBubble content={msg.content} t={t} dark={dark} isUser={true} />
    switch (contentType) {
      case 'image':
      case 'image_md': return <ImageBubble content={msg.content} t={t} dark={dark} />
      case 'issue_viz': return parsedData ? <IssueVizBubble data={parsedData} t={t} dark={dark} onFollowUp={onFollowUp} /> : <TextBubble content={msg.content} t={t} dark={dark} isUser={false} />
      case 'chart': return parsedData ? <ChartBubble data={parsedData} t={t} dark={dark} /> : <TextBubble content={msg.content} t={t} dark={dark} isUser={false} />
      default: return <TextBubble content={msg.content} t={t} dark={dark} isUser={false} />
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: 8, padding: '6px 16px' }}>
      {!isUser && (
        <div style={{ width: 24, height: 24, borderRadius: '50%', flexShrink: 0, background: msg.isError ? '#ef444422' : t.accent + '22', border: `1px solid ${msg.isError ? '#ef444444' : t.accent + '44'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: 2 }}>
          <span style={{ fontSize: 9, color: msg.isError ? '#ef4444' : t.accentText, fontWeight: 700 }}>PG</span>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxWidth: '80%' }}>
        {renderContent()}
        {msg.isError && (
            <button onClick={() => onFollowUp("retry_last")} style={{ alignSelf: 'flex-start', padding: '4px 8px', fontSize: 10, background: dark ? '#2a1010' : '#fee2e2', color: '#ef4444', border: '1px solid #ef444466', borderRadius: 6, cursor: 'pointer', marginTop: 4 }}>
                ↻ Retry Request
            </button>
        )}
      </div>
    </div>
  )
}

// ── Typing indicator ──────────────────────────────────────────────────────────
function TypingIndicator({ t }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px' }}>
      <div style={{ width: 24, height: 24, borderRadius: '50%', background: t.accent + '22', border: `1px solid ${t.accent}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <span style={{ fontSize: 9, color: t.accentText, fontWeight: 700 }}>PG</span>
      </div>
      <div style={{ display: 'flex', gap: 4 }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ width: 5, height: 5, borderRadius: '50%', background: t.accent, animation: 'pgBounce 1.2s ease-in-out infinite', animationDelay: `${i * 0.2}s` }} />
        ))}
      </div>
      <style>{`@keyframes pgBounce{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-4px);opacity:1}}`}</style>
    </div>
  )
}

// ── File chip ─────────────────────────────────────────────────────────────────
function FileChip({ file, onRemove, t, dark }) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 6, background: dark ? '#1e2535' : '#f0f4ff', border: `1px solid ${t.border}`, fontSize: 11, color: t.text2, maxWidth: 180 }}>
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={t.accentText} strokeWidth="2.5" strokeLinecap="round">
        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
        <polyline points="13 2 13 9 20 9" />
      </svg>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
      <button onClick={() => onRemove(file.name)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.text3, padding: 0, lineHeight: 1, fontSize: 13 }}>×</button>
    </div>
  )
}

// ── No API Key Modal ──────────────────────────────────────────────────────────
function NoApiKeyModal({ t, dark, onClose }) {
  const mutedText = dark ? '#6b7280' : '#888'
  const panelBg = dark ? '#0f1318' : '#ffffff'
  const panelBord = dark ? '#1e2a3a' : '#e2e2e2'
  const openApiPanel = () => { window.dispatchEvent(new CustomEvent('prguard:openApiPanel')); onClose() }
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 99999, background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(3px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ width: 400, background: panelBg, border: `1px solid ${panelBord}`, borderRadius: 16, overflow: 'hidden', boxShadow: '0 24px 64px rgba(0,0,0,0.6)' }}>
        <div style={{ padding: '18px 20px 14px', borderBottom: `1px solid ${dark ? '#161e28' : '#f0f0f0'}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 28, height: 28, borderRadius: 8, background: '#f59e0b22', border: '1px solid #f59e0b55', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="7.5" cy="15.5" r="5.5" /><path d="M21 2l-9.6 9.6" /><path d="M15.5 7.5l3 3L22 7l-3-3" />
                </svg>
              </div>
              <span style={{ fontSize: 14, fontWeight: 600, color: t.text }}>API Key Required</span>
            </div>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: mutedText, fontSize: 18, lineHeight: 1 }}
              onMouseEnter={e => e.currentTarget.style.color = t.text} onMouseLeave={e => e.currentTarget.style.color = mutedText}>×</button>
          </div>
          <p style={{ fontSize: 11, color: mutedText, marginTop: 6, lineHeight: 1.6 }}>Connect an LLM provider to start chatting with your codebase.</p>
        </div>
        <div style={{ padding: '20px' }}>
          <div style={{ display: 'flex', gap: 10, padding: '12px 14px', borderRadius: 10, background: '#f59e0b0d', border: '1px solid #f59e0b33', marginBottom: 18 }}>
            <span style={{ fontSize: 16, flexShrink: 0 }}>⚠️</span>
            <div>
              <p style={{ fontSize: 12, fontWeight: 600, color: '#f59e0b', marginBottom: 2 }}>No API key detected</p>
              <p style={{ fontSize: 11, color: mutedText, lineHeight: 1.6 }}>PRGuard uses your API key to call the LLM via the backend. Your key is encrypted and stored server-side per account.</p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 6, marginBottom: 18 }}>
            {[{ label: 'Claude Sonnet', color: '#d97706', recommended: true }, { label: 'GPT-4o', color: '#10b981', recommended: false }, { label: 'Gemini 1.5', color: '#3b82f6', recommended: false }].map(p => (
              <div key={p.label} style={{ flex: 1, padding: '8px 10px', borderRadius: 8, background: dark ? '#0a0e13' : '#f8f8f8', border: `1px solid ${dark ? '#1e2a3a' : '#e8e8e8'}`, textAlign: 'center' }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: p.color, margin: '0 auto 5px' }} />
                <div style={{ fontSize: 10, fontWeight: 500, color: t.text2 }}>{p.label}</div>
                {p.recommended && <div style={{ fontSize: 9, color: t.accentText, marginTop: 2 }}>recommended</div>}
              </div>
            ))}
          </div>

          <button onClick={openApiPanel}
            style={{ width: '100%', padding: '11px', borderRadius: 9, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: t.accentBg, color: t.accentFg, border: `1px solid ${t.accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, transition: 'opacity 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.opacity = '0.85'} onMouseLeave={e => e.currentTarget.style.opacity = '1'}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="7.5" cy="15.5" r="5.5" /><path d="M21 2l-9.6 9.6" /><path d="M15.5 7.5l3 3L22 7l-3-3" />
            </svg>
            Connect API Key
          </button>
          <p style={{ textAlign: 'center', fontSize: 10, color: mutedText, marginTop: 10 }}>🔒 Encrypted at rest · Scoped to your account</p>
        </div>
      </div>
    </div>
  )
}

// ── Connect Repository Modal ──────────────────────────────────────────────────
export function ConnectRepoModal({ t, dark, onClose, onConnect }) {
  const [githubRepos, setGithubRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [connecting, setConnecting] = useState(null) 

  useEffect(() => {
    const loadGithubRepos = async () => {
      try {
        const { getGithubRepos } = await import('../api/client')
        const data = await getGithubRepos()
        setGithubRepos(data)
      } catch (err) {
        console.error('Failed to fetch GH repos:', err)
      } finally {
        setLoading(false)
      }
    }
    loadGithubRepos()
  }, [])

  const handleConnect = async (repo) => {
    setConnecting(repo.id)
    try {
      const { connectRepo } = await import('../api/client')
      await connectRepo(repo.id, repo.name)
      onConnect({ ...repo, indexed: false }) 
      onClose()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to connect repository')
    } finally {
      setConnecting(null)
    }
  }

  const filtered = githubRepos.filter(r => 
    r.name.toLowerCase().includes(search.toLowerCase())
  ).slice(0, 50)

  const mutedText = dark ? '#6b7280' : '#888'
  const inputBg = dark ? '#121922' : '#f5f7fa'
  const panelBg = dark ? '#0f1318' : '#ffffff'
  const panelBord = dark ? '#1e2a3a' : '#e2e2e2'
  const rowHover = dark ? '#1a222c' : '#f8f9fb'

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 99999, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      
      <div style={{ 
        width: 480, height: 600, background: panelBg, border: `1px solid ${panelBord}`, 
        borderRadius: 20, overflow: 'hidden', boxShadow: '0 32px 64px rgba(0,0,0,0.5)',
        display: 'flex', flexDirection: 'column'
      }}>
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${dark ? '#1e2a3a' : '#f0f0f0'}`, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 32, height: 32, borderRadius: 10, background: t.accent + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={t.accentText} strokeWidth="2.5" strokeLinecap="round">
                  <path d="M12 2C6.477 2 2 6.477 2 12c0 4.418 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.604-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.92.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z" />
                </svg>
              </div>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: t.text }}>Connect Repository</h2>
            </div>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: mutedText, fontSize: 24, lineHeight: 1 }}
              onMouseEnter={e => e.currentTarget.style.color = t.text} onMouseLeave={e => e.currentTarget.style.color = mutedText}>×</button>
          </div>
          <p style={{ fontSize: 13, color: mutedText, margin: 0 }}>Select a repository to authorize PRGuard access.</p>
        </div>

        <div style={{ padding: '16px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 12, background: inputBg, border: `1px solid ${panelBord}` }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={mutedText} strokeWidth="2.5" strokeLinecap="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input 
              value={search} 
              onChange={e => setSearch(e.target.value)}
              placeholder="Search repositories..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: t.text }}
            />
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px 20px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <div style={{ width: 20, height: 20, border: `2px solid ${t.accent}33`, borderTopColor: t.accent, borderRadius: '50%', animation: 'pgSpin 0.8s linear infinite', margin: '0 auto 12px' }} />
              <p style={{ fontSize: 12, color: mutedText }}>Fetching repositories...</p>
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px 20px' }}>
              <p style={{ fontSize: 13, color: mutedText }}>No repositories found.</p>
            </div>
          ) : (
            filtered.map(repo => (
              <div key={repo.id} 
                style={{ 
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', 
                  padding: '12px 16px', borderRadius: 12, margin: '2px 0',
                  transition: 'background 0.2s', cursor: 'default'
                }}
                onMouseEnter={e => e.currentTarget.style.background = rowHover}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: t.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{repo.name}</span>
                    {repo.private && <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 4, background: dark ? '#2a2010' : '#fff3cd', color: '#856404', border: '1px solid currentColor' }}>Private</span>}
                  </div>
                  {repo.description && <div style={{ fontSize: 11, color: mutedText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{repo.description}</div>}
                </div>
                
                <button 
                  onClick={() => handleConnect(repo)}
                  disabled={connecting === repo.id}
                  style={{ 
                    padding: '7px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, 
                    cursor: connecting ? 'wait' : 'pointer', 
                    background: connecting === repo.id ? 'transparent' : t.accentBg, 
                    color: connecting === repo.id ? t.text3 : t.accentFg, 
                    border: `1px solid ${connecting === repo.id ? panelBord : t.accent}`,
                    transition: 'all 0.15s', marginLeft: 16
                  }}
                  onMouseEnter={e => { if (!connecting) e.currentTarget.style.opacity = '0.85' }}
                  onMouseLeave={e => { if (!connecting) e.currentTarget.style.opacity = '1' }}
                >
                  {connecting === repo.id ? 'Connecting...' : 'Connect'}
                </button>
              </div>
            ))
          )}
        </div>

        <div style={{ padding: '16px 24px', background: rowHover, borderTop: `1px solid ${panelBord}`, flexShrink: 0 }}>
          <p style={{ fontSize: 11, color: mutedText, lineHeight: 1.5, margin: 0 }}>
            Only selected repositories will be indexed for search and review. You can disconnect them at any time from the sidebar.
          </p>
        </div>
      </div>
      
      <style>{`
        @keyframes pgSpin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}

// ── Main ChatPanel ────────────────────────────────────────────────────────────
export default function ChatPanel({ selectedRepo, selectedIssue, connectedRepos = [], chatInput, setChatInput, autoSend, setAutoSend, onRepoConnect }) {
  const { theme } = useContext(ThemeContext)
  const t = getTheme(theme)
  const dark = theme === 'dark'
  const repoLabel = typeof selectedRepo === 'string' ? selectedRepo.trim() : (selectedRepo ? String(selectedRepo).trim() : '')
  const hasRepo = Boolean(repoLabel)
  const hasConnectedRepos = Array.isArray(connectedRepos) && connectedRepos.length > 0
  const headerText = !hasRepo
    ? 'Select a repository to get started'
    : selectedIssue
      ? `Issue #${selectedIssue.number} · ${repoLabel}`
      : `Chatting about ${repoLabel}`
  const headerDotColor = !hasRepo ? (dark ? '#6b7280' : '#f59e0b') : '#22c55e'

  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const [noKeyModal, setNoKeyModal] = useState(false)
  const [selectedModel, setSelectedModel] = useState(() => {
    const saved = getScopedProvider()
    return MODELS.find(m => m.id === saved) || MODELS[0]
  })
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [attachedFiles, setAttachedFiles] = useState([])
  const [connectOpen, setConnectOpen] = useState(false)
  const [plusMenuOpen, setPlusMenuOpen] = useState(false)
  const [vizMode, setVizMode] = useState(false)
  const [repoHint, setRepoHint] = useState('')

  const bottomRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const modelBtnRef = useRef(null)
  const plusBtnRef = useRef(null)
  const activeRequestRef = useRef(null)

  const { hasKey, loading: keyLoading } = useApiKeyGuard()
  const noKey = !hasKey

  useEffect(() => {
    if (!keyLoading && !hasKey) {
      setNoKeyModal(true)
    }
  }, [hasKey, keyLoading])

  useEffect(() => {
    if (selectedModel?.id && getScopedProvider() !== selectedModel.id) {
      setScopedProvider(selectedModel.id)
    }
  }, [selectedModel])

  useEffect(() => {
    const check = () => {
      const saved = getScopedProvider()
      if (saved && saved !== selectedModel.id) {
        const found = MODELS.find(m => m.id === saved)
        if (found) setSelectedModel(found)
      }
    }
    const timer = setInterval(check, 500)
    return () => clearInterval(timer)
  }, [selectedModel])

  useEffect(() => {
    setMessages([])
    setAttachedFiles([])
    setChatInput('')
    setRepoHint('')
  }, [selectedRepo, setChatInput])

  useEffect(() => {
    if (hasRepo) {
      setRepoHint('')
    }
  }, [hasRepo])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  useEffect(() => {
    if (autoSend && chatInput?.trim()) {
      const timer = setTimeout(() => {
        if (selectedIssue) sendVisualization()
        else sendMessage(chatInput)
        setAutoSend(false)
      }, 80)
      return () => clearTimeout(timer)
    }
  }, [autoSend, chatInput])

  useEffect(() => {
    if (chatInput && !autoSend) textareaRef.current?.focus()
    // Reset height when chatInput is cleared (e.g. after sending message)
    if (!chatInput && textareaRef.current) {
        textareaRef.current.style.height = '80px'
    }
  }, [chatInput])

  useEffect(() => {
    const handler = (e) => {
      if (modelBtnRef.current && !modelBtnRef.current.contains(e.target)) setModelMenuOpen(false)
      if (plusBtnRef.current && !plusBtnRef.current.contains(e.target)) setPlusMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    return () => {
      if (activeRequestRef.current) {
        activeRequestRef.current.abort()
      }
    }
  }, [])

  const sendVisualization = async () => {
    if (!selectedRepo) {
      if (!hasConnectedRepos) {
        setConnectOpen(true)
      } else {
        setRepoHint('Select a repository from the sidebar to start chatting.')
      }
      return
    }
    if (loading) return
    if (noKey) { setNoKeyModal(true); return }

    const userMsg = {
      role: 'user',
      content: selectedIssue
        ? `⬡ Visualize Issue #${selectedIssue.number}: "${selectedIssue.title}"`
        : `⬡ Visualize repository: "${selectedRepo}"`,
    }
    setMessages(prev => [...prev, userMsg])
    setChatInput('')
    setLoading(true)
    const controller = new AbortController()
    activeRequestRef.current = controller

    try {
      const vizPrompt = selectedIssue
        ? `Analyze issue #${selectedIssue.number}: "${selectedIssue.title}" and return ONLY a valid JSON object — no markdown, no explanation, no code fences. Return exactly this shape:
{
  "type": "issue_analysis",
  "severity": "High|Medium|Low",
  "effort": "~1h|~2h|~4h|~8h",
  "root_cause": "one clear sentence about the root cause",
  "fix_summary": "one clear sentence about how to fix it",
  "files": [{ "path": "routes/auth.py", "role": "Primary fix", "weight": 0.9 }],
  "steps": ["step 1", "step 2", "step 3"],
  "related": [{ "number": 1234, "title": "Related issue title", "note": "why related" }],
  "chart": { "labels": ["Bug", "Auth", "Security", "Performance"], "values": [40, 30, 20, 10] }
}`
        : `Analyze repository "${selectedRepo}" and return ONLY a valid JSON object — no markdown, no explanation, no code fences. Return exactly this shape:
{
  "type": "chart",
  "title": "Repository Analysis",
  "labels": ["Architecture", "Maintainability", "Test Coverage", "Security", "Performance"],
  "values": [75, 68, 52, 70, 64]
}`

      const result = await apiSendMessage(
        vizPrompt,
        selectedRepo,
        selectedIssue?.number || null,
        [],
        { signal: controller.signal, provider: selectedModel.id },
      )
      const assistantText = result?.message || result?.answer || ''

      if (!assistantText) {
        throw new Error("The AI failed to generate an analysis. Please check your API key and repository status.")
      }

      try {
        const parsed = JSON.parse(assistantText.trim())
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: parsed.type === 'issue_analysis' ? assistantText.trim() : assistantText,
        }])
      } catch (err) {
        setMessages(prev => [...prev, { role: 'assistant', content: assistantText }])
      }

    } catch (err) {
      if (err?.message?.toLowerCase?.().includes('canceled')) {
        setMessages(prev => [...prev, { role: 'assistant', content: '⏹ Request stopped.', isError: false }])
        return
      }
      if (err.message && err.message.toLowerCase().includes('api key')) {
        setNoKeyModal(true)
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `🚨 **Error**: ${err.message}`, isError: true }])
      }
    } finally {
      activeRequestRef.current = null
      setLoading(false)
    }
  }

  const sendMessage = async (text, historyOverride = null) => {
    const content = (text ?? chatInput ?? '').trim()
    if (!selectedRepo || !content || loading) {
      if (!selectedRepo) {
        if (!hasConnectedRepos) {
          setConnectOpen(true)
        } else {
          setRepoHint('Select a repository from the sidebar to start chatting.')
        }
      }
      return
    }
    if (noKey) { setNoKeyModal(true); return }

    setChatInput('')
    const effectiveHistory = Array.isArray(historyOverride) ? historyOverride : messages
    const userMsg = {
      role: 'user',
      content: attachedFiles.length > 0
        ? `${content}\n\n[Attached: ${attachedFiles.map(f => f.name).join(', ')}]`
        : content,
    }
    const newMessages = [...effectiveHistory, userMsg]
    setMessages(newMessages)
    setAttachedFiles([])
    setLoading(true)
    const controller = new AbortController()
    activeRequestRef.current = controller

    try {
      const result = await apiSendMessage(
        content,
        selectedRepo,
        selectedIssue?.number || null,
        effectiveHistory,
        { signal: controller.signal, provider: selectedModel.id },
      )
      const assistantText = result?.message || result?.answer || ''

      if (!assistantText) {
        throw new Error("No response received from AI. Check your connection or API key.")
      }

      setMessages(prev => [...prev, { role: 'assistant', content: assistantText }])

    } catch (err) {
      if (err?.message?.toLowerCase?.().includes('canceled')) {
        setMessages(prev => [...prev, { role: 'assistant', content: '⏹ Request stopped.', isError: false }])
        return
      }
      if (err?.message?.toLowerCase?.().includes('api key')) {
        setNoKeyModal(true)
        return
      }
      setMessages(prev => [...prev, { role: 'assistant', content: `🚨 **Error**: ${err.message}`, isError: true }])
    } finally {
      activeRequestRef.current = null
      setLoading(false)
    }
  }

  const stopCurrentRequest = () => {
    if (activeRequestRef.current) {
      activeRequestRef.current.abort()
      activeRequestRef.current = null
    }
    setLoading(false)
  }

  const handleFollowUp = (prompt) => {
    if (prompt === "retry_last") {
        const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')
        if (!lastUserMsg) return
        const assistantErrorIdx = [...messages]
          .map((m, i) => ({ m, i }))
          .reverse()
          .find(x => x.m.role === 'assistant' && x.m.isError)?.i
        const filtered = assistantErrorIdx === undefined
          ? messages
          : messages.filter((_, i) => i !== assistantErrorIdx)
        setMessages(filtered)
        sendMessage(lastUserMsg.content, filtered)
        return
    }
    sendMessage(prompt) 
  }

  const handleFileAttach = (e) => {
    const files = Array.from(e.target.files || [])
    setAttachedFiles(prev => [...prev, ...files.map(f => ({ name: f.name, size: f.size }))])
    e.target.value = ''
    setPlusMenuOpen(false)
  }

  const handleInput = (e) => {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
  }

  const isEmpty = messages.length === 0
  const mutedText = dark ? '#6b7280' : '#888'
  const inputBg = dark ? '#13161b' : '#ffffff'
  const barBg = dark ? '#0d0f12' : '#f0f2f5'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: t.bg, overflow: 'hidden', position: 'relative' }}>

      {/* Header */}
      <div style={{ padding: '10px 16px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: headerDotColor, flexShrink: 0 }} />
        <span style={{ fontSize: 12, color: t.text2 }}>
          {headerText}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', background: dark ? '#1e2535' : '#f0f0f0', borderRadius: 7, padding: 2, gap: 1 }}>
          {[{ id: false, label: 'Chat' }, { id: true, label: selectedIssue ? '⬡ Visualize' : '⬡ Repo Visualize' }].map(opt => (
            <button key={String(opt.id)} onClick={() => setVizMode(opt.id)}
              style={{ padding: '3px 10px', borderRadius: 5, fontSize: 10, fontWeight: 500, cursor: 'pointer', border: 'none', transition: 'all 0.15s', background: vizMode === opt.id ? (dark ? t.accent : '#fff') : 'transparent', color: vizMode === opt.id ? (dark ? t.accentFg : t.accentText) : t.text3, boxShadow: vizMode === opt.id ? '0 1px 3px rgba(0,0,0,0.15)' : 'none' }}>
              {opt.label}
            </button>
          ))}
        </div>

        {chatInput && !autoSend && !selectedIssue && (
          <span style={{ marginLeft: 'auto', fontSize: 10, padding: '2px 8px', borderRadius: 4, background: t.accent + '18', color: t.accentText, border: `1px solid ${t.accent}44` }}>
            ✦ pre-filled — edit or press Enter
          </span>
        )}
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {isEmpty && (
          <div style={{ padding: '16px 16px 8px' }}>
            <div style={{ background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 12, padding: '14px 16px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: t.accentText, marginBottom: 8 }}>PRGUARD AI</div>
              {!hasRepo ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <p style={{ fontSize: 13, color: t.text, lineHeight: 1.65, margin: 0 }}>
                    {hasConnectedRepos
                      ? 'Select a repository from the sidebar to start chatting.'
                      : 'Connect a repository to start chatting.'}
                  </p>
                  <button
                    onClick={() => {
                      if (hasConnectedRepos) {
                        setRepoHint('Select a repository from the sidebar to start chatting.')
                        return
                      }
                      setConnectOpen(true)
                    }}
                    style={{ alignSelf: 'flex-start', padding: '9px 12px', fontSize: 12, fontWeight: 600, color: t.accentFg, background: t.accentBg, border: `1px solid ${t.accent}`, borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s' }}
                  >
                    {hasConnectedRepos ? 'Select from sidebar' : 'Connect a repository'}
                  </button>
                </div>
              ) : (
                <p style={{ fontSize: 13, color: t.text, lineHeight: 1.65, margin: 0 }}>
                  Hello! I am ready to help you understand this repository. Ask me anything — or click an <strong>issue</strong> or <strong>file</strong> on the left to instantly ask about it.
                  {selectedIssue && <><br /><br />Click <strong>⬡ Visualize</strong> above to get an AI-powered analysis with charts, file breakdown, and fix steps.</>}
                </p>
              )}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} t={t} dark={dark} onFollowUp={handleFollowUp} />
        ))}
        {loading && <TypingIndicator t={t} />}

        {!hasRepo && repoHint && (
          <div style={{ padding: '0 16px 8px' }}>
            <div style={{ fontSize: 11, color: dark ? '#fbbf24' : '#b45309', background: dark ? '#f59e0b14' : '#fef3c7', border: `1px solid ${dark ? '#f59e0b33' : '#f59e0b55'}`, borderRadius: 8, padding: '8px 10px' }}>
              {repoHint}
            </div>
          </div>
        )}

        {noKey && !loading && messages.length === 0 && (
          <div style={{ padding: '6px 16px' }}>
            <div style={{ fontSize: 11, color: '#f59e0b', background: '#f59e0b11', border: '1px solid #f59e0b33', borderRadius: 6, padding: '6px 10px', cursor: 'pointer' }}
              onClick={() => setNoKeyModal(true)}>
              ⚠ No API key — <strong style={{ textDecoration: 'underline' }}>click here to connect one</strong>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestion chips */}
      {isEmpty && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, padding: '0 16px 10px', flexShrink: 0 }}>
          {hasRepo ? (
            <button onClick={sendVisualization} disabled={!selectedRepo || loading || noKey}
              style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '9px 12px', fontSize: 12, fontWeight: 600, color: t.accentFg, background: t.accentBg, border: `1px solid ${t.accent}`, borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s' }}>
              {selectedIssue ? `⬡ Visualize Issue #${selectedIssue.number} with AI` : '⬡ Visualize Repository with AI'}
            </button>
          ) : (
            <button
              onClick={() => {
                if (hasConnectedRepos) {
                  setRepoHint('Select a repository from the sidebar to start chatting.')
                  return
                }
                setConnectOpen(true)
              }}
              style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '9px 12px', fontSize: 12, fontWeight: 600, color: t.accentFg, background: t.accentBg, border: `1px solid ${t.accent}`, borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s' }}
            >
              {hasConnectedRepos ? 'Select a repository from the sidebar' : 'Connect a repository'}
            </button>
          )}
          {hasRepo && SUGGESTED.map((s, i) => (
            <button key={i} onClick={() => { if (noKey) { setNoKeyModal(true); return } sendMessage(s) }}
              style={{ textAlign: 'left', padding: '8px 12px', fontSize: 11, color: t.text3, background: dark ? '#13161b' : '#fff', border: `1px solid ${t.border}`, borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = t.accent; e.currentTarget.style.color = t.accentText }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.text3 }}>
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input bar */}
      <div style={{ padding: '10px 14px 12px', borderTop: `1px solid ${t.border}`, background: barBg, flexShrink: 0 }}>

        {attachedFiles.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {attachedFiles.map(f => (
              <FileChip key={f.name} file={f} t={t} dark={dark}
                onRemove={name => setAttachedFiles(prev => prev.filter(x => x.name !== name))} />
            ))}
          </div>
        )}

        {vizMode ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={sendVisualization} disabled={!selectedRepo || loading}
              style={{ flex: 1, padding: '10px', borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: !selectedRepo || loading ? 'not-allowed' : 'pointer', background: !selectedRepo || loading ? (dark ? '#1e2535' : '#e8e8e8') : t.accentBg, color: !selectedRepo || loading ? mutedText : t.accentFg, border: `1px solid ${!selectedRepo || loading ? t.border : t.accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, transition: 'all 0.15s' }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
              {loading ? 'Analyzing...' : (selectedIssue ? `Analyze Issue #${selectedIssue.number}` : 'Analyze Repository')}
            </button>
            <button onClick={() => setVizMode(false)}
              style={{ padding: '10px 14px', borderRadius: 10, fontSize: 12, cursor: 'pointer', background: 'transparent', color: t.text3, border: `1px solid ${t.border}` }}>
              Chat instead
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, background: inputBg, border: `1px solid ${chatInput ? t.accent : t.border}`, borderRadius: 12, padding: '8px 8px 8px 6px', transition: 'border-color 0.15s' }}>

            <div style={{ position: 'relative', flexShrink: 0 }} ref={plusBtnRef}>
              <button onClick={() => setPlusMenuOpen(p => !p)} title="Attach or connect"
                style={{ width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', background: plusMenuOpen ? (dark ? '#1e2535' : '#e8e8e8') : 'transparent', border: `1px solid ${plusMenuOpen ? t.border : 'transparent'}`, color: t.text3, transition: 'all 0.15s', flexShrink: 0 }}
                onMouseEnter={e => { e.currentTarget.style.background = dark ? '#1e2535' : '#e8e8e8'; e.currentTarget.style.color = t.text }}
                onMouseLeave={e => { if (!plusMenuOpen) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = t.text3 } }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              </button>
              {plusMenuOpen && (
                <div style={{ position: 'absolute', bottom: '100%', left: 0, marginBottom: 6, background: dark ? '#0f1318' : '#fff', border: `1px solid ${dark ? '#1e2a3a' : '#e2e2e2'}`, borderRadius: 10, overflow: 'hidden', width: 210, boxShadow: dark ? '0 -8px 24px rgba(0,0,0,0.6)' : '0 -4px 16px rgba(0,0,0,0.1)', zIndex: 100 }}>
                  {[
                    { icon: '📎', label: 'Attach file', desc: 'Upload a file to discuss', action: () => fileInputRef.current?.click() },
                    {
                      icon: '📁',
                      label: hasConnectedRepos ? 'Select repository' : 'Connect Repository',
                      desc: hasConnectedRepos ? 'Pick a repo from the sidebar' : 'Index a GitHub repo',
                      action: () => {
                        if (hasConnectedRepos) {
                          setRepoHint('Select a repository from the sidebar to start chatting.')
                          setPlusMenuOpen(false)
                          return
                        }
                        setConnectOpen(true)
                        setPlusMenuOpen(false)
                      },
                    },
                    { icon: '⬡', label: 'Visualize issue', desc: 'AI chart + analysis', action: () => { setVizMode(true); setPlusMenuOpen(false) } },
                  ].map((item, i) => (
                    <button key={i} onClick={item.action}
                      style={{ width: '100%', textAlign: 'left', padding: '10px 12px', display: 'flex', alignItems: 'flex-start', gap: 10, background: 'transparent', border: 'none', cursor: 'pointer', borderBottom: i < 2 ? `1px solid ${dark ? '#161e28' : '#f0f0f0'}` : 'none', transition: 'background 0.12s' }}
                      onMouseEnter={e => e.currentTarget.style.background = dark ? '#1e2535' : '#f5f5f5'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                      <span style={{ fontSize: 15, flexShrink: 0, marginTop: 1 }}>{item.icon}</span>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 500, color: t.text }}>{item.label}</div>
                        <div style={{ fontSize: 10, color: mutedText, marginTop: 1 }}>{item.desc}</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <textarea ref={textareaRef} value={chatInput ?? ''}
              onChange={e => setChatInput(e.target.value)}
              onInput={handleInput}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
              placeholder={!hasRepo
                ? (hasConnectedRepos
                  ? 'Select a repository from the sidebar to start chatting...'
                  : 'Connect a repository to start chatting...')
                : noKey
                  ? 'Please add an API key in settings to chat...'
                  : 'Ask anything about this codebase... or click an issue / file →'}
              disabled={!hasRepo || noKey || loading}
              rows={1}
              style={{ flex: 1, resize: 'none', outline: 'none', background: 'transparent', border: 'none', padding: '4px 4px', fontSize: 13, fontFamily: 'inherit', color: t.text, lineHeight: 1.55, minHeight: 80, maxHeight: 200, overflowY: 'auto', cursor: !hasRepo || noKey ? 'not-allowed' : 'text', opacity: !hasRepo || noKey ? 0.6 : 1 }} />

            <div style={{ position: 'relative', flexShrink: 0 }} ref={modelBtnRef}>
              <button onClick={() => setModelMenuOpen(p => !p)}
                style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 8px', borderRadius: 7, background: modelMenuOpen ? (dark ? '#1e2535' : '#e8e8e8') : (dark ? '#1a2030' : '#f0f0f0'), border: `1px solid ${dark ? '#2a3a50' : '#d8d8d8'}`, cursor: 'pointer', fontSize: 11, fontWeight: 500, color: t.text2, transition: 'all 0.15s', whiteSpace: 'nowrap' }}
                onMouseEnter={e => e.currentTarget.style.background = dark ? '#1e2535' : '#e4e4e4'}
                onMouseLeave={e => e.currentTarget.style.background = modelMenuOpen ? (dark ? '#1e2535' : '#e8e8e8') : (dark ? '#1a2030' : '#f0f0f0')}>
                <span>{selectedModel.label}</span>
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ opacity: 0.5 }}>
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
              {modelMenuOpen && (
                <div style={{ position: 'absolute', bottom: '100%', right: 0, marginBottom: 6, background: dark ? '#0f1318' : '#fff', border: `1px solid ${dark ? '#1e2a3a' : '#e2e2e2'}`, borderRadius: 10, overflow: 'hidden', width: 220, boxShadow: dark ? '0 -8px 24px rgba(0,0,0,0.6)' : '0 -4px 16px rgba(0,0,0,0.1)', zIndex: 100 }}>
                  <div style={{ padding: '8px 12px 6px', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: mutedText, borderBottom: `1px solid ${dark ? '#161e28' : '#f0f0f0'}` }}>Select model</div>
                  {MODELS.map(model => (
                    <button key={model.id} onClick={() => { setSelectedModel(model); setModelMenuOpen(false) }}
                      style={{ width: '100%', textAlign: 'left', padding: '9px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: selectedModel.id === model.id ? (dark ? '#1e2535' : '#f5f5f5') : 'transparent', border: 'none', borderBottom: `1px solid ${dark ? '#161e28' : '#f5f5f5'}`, cursor: 'pointer', transition: 'background 0.12s' }}
                      onMouseEnter={e => { if (selectedModel.id !== model.id) e.currentTarget.style.background = dark ? '#1a2030' : '#f8f8f8' }}
                      onMouseLeave={e => { if (selectedModel.id !== model.id) e.currentTarget.style.background = 'transparent' }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: selectedModel.id === model.id ? 600 : 400, color: selectedModel.id === model.id ? t.accentText : t.text }}>{model.label}</div>
                        <div style={{ fontSize: 10, color: mutedText, marginTop: 1 }}>{model.sub}</div>
                      </div>
                      {selectedModel.id === model.id && (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={t.accentText} strokeWidth="2.5" strokeLinecap="round"><polyline points="20 6 9 17 4 12" /></svg>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {loading ? (
              <button onClick={stopCurrentRequest}
                title="Stop request"
                style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', background: dark ? '#3b1111' : '#fee2e2', border: '1px solid #ef4444aa', transition: 'all 0.15s', color: '#ef4444' }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <rect x="6" y="6" width="12" height="12" rx="1.5" />
                </svg>
              </button>
            ) : (
              <button onClick={() => sendMessage()} disabled={!hasRepo || noKey || !(chatInput ?? '').trim() || loading}
                style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: (chatInput ?? '').trim() && !loading && !noKey && hasRepo ? 'pointer' : 'not-allowed', background: (chatInput ?? '').trim() && !loading && !noKey && hasRepo ? t.accent : (dark ? '#1e2535' : '#e8eaf0'), border: `1px solid ${(chatInput ?? '').trim() && !loading && !noKey && hasRepo ? t.accent : t.border}`, transition: 'all 0.15s', color: (chatInput ?? '').trim() && !loading && !noKey && hasRepo ? t.accentFg : t.text3 }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            )}
          </div>
        )}

        <input ref={fileInputRef} type="file" multiple style={{ display: 'none' }} onChange={handleFileAttach} />
        <p style={{ fontSize: 10, color: dark ? '#2a3a50' : '#ccc', textAlign: 'center', marginTop: 6 }}>
          Enter to send · Shift+Enter for new line · Click + to attach or connect a repo
        </p>
      </div>

      {noKeyModal && <NoApiKeyModal t={t} dark={dark} onClose={() => setNoKeyModal(false)} />}
      {connectOpen && <ConnectRepoModal t={t} dark={dark} onClose={() => setConnectOpen(false)} onConnect={(repo) => onRepoConnect?.(repo)} />}
    </div>
  )
}