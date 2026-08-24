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

export const getTheme = (theme) => {
  if (theme === 'light') {
    return {
      bg:         '#f0f2f5',
      bg2:        '#ffffff',
      bg3:        '#e8eaf0',
      border:     '#c8ccd8',
      accent:     '#d4860a',
      accentText: '#b36d00',
      accentBg:   '#d4860a',
      accentFg:   '#ffffff',
      text:       '#0f1117',
      text2:      '#2d3142',
      text3:      '#6b7280',
      green:      '#16a34a',
      red:        '#dc2626',
      blue:       '#2563eb',
    }
  }
  return {
    bg:         '#0d0f12',
    bg2:        '#0f1217',
    bg3:        '#13161b',
    border:     '#2a2f3d',
    accent:     '#e8a020',
    accentText: '#e8a020',
    accentBg:   '#e8a020',
    accentFg:   '#0d0f12',
    text:       '#e8e4d9',
    text2:      '#8b8fa8',
    text3:      '#555970',
    green:      '#2ecc71',
    red:        '#e74c3c',
    blue:       '#4a9eff',
  }
}
 

export const getLabelColors = (theme, label) => {
  const dark = {
    bug:               'bg-red-900/30 text-red-400 border-red-800',
    feature:           'bg-green-900/30 text-green-400 border-green-800',
    'good first issue':'bg-amber-900/30 text-amber-400 border-amber-800',
    documentation:     'bg-blue-900/30 text-blue-400 border-blue-800',
    default:           'bg-gray-800 text-gray-400 border-gray-700',
  }
  const light = {
    bug:               'bg-red-100 text-red-700 border-red-300',
    feature:           'bg-green-100 text-green-700 border-green-300',
    'good first issue':'bg-amber-100 text-amber-700 border-amber-300',
    documentation:     'bg-blue-100 text-blue-700 border-blue-300',
    default:           'bg-gray-100 text-gray-600 border-gray-300',
  }
  const map = theme === 'light' ? light : dark
  return map[label] || map.default
}