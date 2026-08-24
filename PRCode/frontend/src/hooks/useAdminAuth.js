import { useEffect, useState } from 'react'
import { adminLogout, getAdminMe } from '../api/client'

const isSafeRedirect = (candidate, fallback) => {
  if (typeof candidate !== 'string' || !candidate.trim()) return fallback
  try {
    if (candidate.startsWith('/') && !candidate.startsWith('//')) {
      return candidate
    }
    const parsed = new URL(candidate, window.location.origin)
    if (parsed.origin === window.location.origin) {
      return `${parsed.pathname}${parsed.search}${parsed.hash}`
    }
  } catch {
    return fallback
  }
  return fallback
}

export const useAdminAuth = () => {
  const [loading, setLoading] = useState(true)
  const [isAdminAuthenticated, setIsAdminAuthenticated] = useState(false)
  const [adminUser, setAdminUser] = useState(null)

  const refresh = async () => {
    try {
      const data = await getAdminMe()
      if (data?.role === 'admin') {
        setAdminUser(data)
        setIsAdminAuthenticated(true)
        localStorage.setItem('prguard_admin_login', data.username || data.email || 'admin')
      } else {
        setAdminUser(null)
        setIsAdminAuthenticated(false)
        localStorage.removeItem('prguard_admin_login')
      }
    } catch {
      setAdminUser(null)
      setIsAdminAuthenticated(false)
      localStorage.removeItem('prguard_admin_login')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const logout = async () => {
    let redirectTarget = '/'
    try {
      const payload = await adminLogout()
      redirectTarget = isSafeRedirect(payload?.redirect, '/')
    } catch {
      // ignore network failures on logout
    } finally {
      setAdminUser(null)
      setIsAdminAuthenticated(false)
      localStorage.removeItem('prguard_admin_login')
      window.location.href = redirectTarget
    }
  }

  return {
    loading,
    isAdminAuthenticated,
    adminUser,
    refresh,
    logout,
  }
}
