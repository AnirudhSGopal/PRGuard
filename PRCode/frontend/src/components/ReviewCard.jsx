import { useState, useContext } from 'react'
import { ThemeContext } from '../App'
import { getTheme } from '../utils/helpers'

function TreeNode({ node, depth = 0, onFileSelect }) {
  const [open, setOpen] = useState(depth === 0)
  const { theme } = useContext(ThemeContext)
  const t = getTheme(theme)

  const name = node.path.replace(/\/$/, '').split('/').pop()
  const fileColors = { python: t.blue, markdown: t.green, javascript: '#e8a020' }

  if (node.type === 'folder') {
    return (
      <div>
        <div
          onClick={() => setOpen(!open)}
          style={{ display: 'flex', alignItems: 'center', gap: 6, paddingLeft: `${8 + depth * 12}px`, paddingTop: 4, paddingBottom: 4, cursor: 'pointer', color: t.accentText, transition: 'background 0.12s' }}
          onMouseEnter={e => e.currentTarget.style.background = t.bg3}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          <span style={{ fontSize: 10, flexShrink: 0 }}>{open ? '▾' : '▸'}</span>
          <span style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}/</span>
        </div>
        {open && node.children?.map((child, i) => (
          <TreeNode key={i} node={child} depth={depth + 1} onFileSelect={onFileSelect} />
        ))}
      </div>
    )
  }

  return (
    <div
      onClick={() => onFileSelect?.(node.path)}
      title={`Ask PRGuard about ${node.path}`}
      style={{ display: 'flex', alignItems: 'center', gap: 6, paddingLeft: `${8 + depth * 12}px`, paddingTop: 4, paddingBottom: 4, cursor: 'pointer', transition: 'background 0.12s', position: 'relative' }}
      onMouseEnter={e => {
        e.currentTarget.style.background = t.bg3
        const badge = e.currentTarget.querySelector('.ask-badge')
        if (badge) badge.style.opacity = '1'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'transparent'
        const badge = e.currentTarget.querySelector('.ask-badge')
        if (badge) badge.style.opacity = '0'
      }}
    >
      <span style={{ fontSize: 10, color: fileColors[node.language] || t.text3, flexShrink: 0 }}>›</span>
      <span style={{ fontSize: 12, color: t.text2, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
      <span className="ask-badge" style={{ opacity: 0, fontSize: 9, padding: '1px 6px', borderRadius: 3, marginRight: 6, color: t.accentText, background: t.accent + '20', border: `1px solid ${t.accent}44`, transition: 'opacity 0.15s', flexShrink: 0 }}>
        ask →
      </span>
    </div>
  )
}

export default function FileTree({ files, onFileSelect }) {
  // ── No scroll here — parent in Dashboard handles it ──
  return (
    <div style={{ paddingTop: 4, paddingBottom: 4 }}>
      {files.map((node, i) => (
        <TreeNode key={i} node={node} onFileSelect={onFileSelect} />
      ))}
    </div>
  )
}