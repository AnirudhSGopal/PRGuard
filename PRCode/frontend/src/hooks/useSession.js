import { useEffect, useState } from 'react'
import { getAdminMe, getMe } from '../api/client'

export const useSession = () => {
  const [loading, setLoading] = useState(true)
  const [sessionRole, setSessionRole] = useState(() => {
    // ✅ Read localStorage immediately on init before any API call
    try {
      const stored = localStorage.getItem('prguard_session')
      if (stored) {
        const parsed = JSON.parse(stored)
        if (parsed?.role === 'user' && parsed?.user_id) return 'user'
      }
    } catch {}
    return null
  })
  const [sessionUser, setSessionUser] = useState(() => {
    // ✅ Read localStorage immediately on init before any API call
    try {
      const stored = localStorage.getItem('prguard_session')
      if (stored) return JSON.parse(stored)
    } catch {}
    return null
  })

  useEffect(() => {
    let active = true

    const loadSession = async () => {
      try {
        const [userSession, adminSession] = await Promise.all([getMe(), getAdminMe()])
        if (!active) return

        if (userSession?.authenticated && userSession?.role === 'user') {
          localStorage.setItem('prguard_session', JSON.stringify(userSession))
          setSessionRole('user')
          setSessionUser(userSession)
          return
        }

        if (adminSession?.role === 'admin') {
          localStorage.removeItem('prguard_session')
          setSessionRole('admin')
          setSessionUser(adminSession)
          return
        }

        // Cookie failed — keep localStorage session if it exists
        const stored = localStorage.getItem('prguard_session')
        if (stored) {
          try {
            const parsed = JSON.parse(stored)
            if (parsed?.role === 'user' && parsed?.user_id) {
              setSessionRole('user')
              setSessionUser(parsed)
              return
            }
          } catch {
            localStorage.removeItem('prguard_session')
          }
        }

        // Truly unauthenticated
        setSessionRole(null)
        setSessionUser(null)

      } catch {
        // On error keep whatever state we have from localStorage
      }
    }

    loadSession().finally(() => {
      if (active) setLoading(false)
    })

    const handleExpiry = () => {
      if (!active) return
      localStorage.removeItem('prguard_session')
      setSessionRole(null)
      setSessionUser(null)
      setLoading(false)
    }

    window.addEventListener('auth:expired', handleExpiry)
    return () => {
      active = false
      window.removeEventListener('auth:expired', handleExpiry)
    }
  }, [])

  return {
    loading,
    sessionRole,
    sessionUser,
    isAuthenticated: sessionRole !== null,
    isAdmin: sessionRole === 'admin',
    isUser: sessionRole === 'user',
  }
}
