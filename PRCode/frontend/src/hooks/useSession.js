import { useEffect, useState } from 'react'
import { getAdminMe, getMe } from '../api/client'

export const useSession = () => {
  const [loading, setLoading] = useState(true)
  const [sessionRole, setSessionRole] = useState(null)
  const [sessionUser, setSessionUser] = useState(null)

  useEffect(() => {
    let active = true

    const loadSession = async () => {
      try {
        const [userSession, adminSession] = await Promise.all([getMe(), getAdminMe()])
        if (!active) return

        if (userSession?.authenticated && userSession?.role === 'user') {
          // ✅ Cookie worked — keep localStorage in sync
          localStorage.setItem('prguard_session', JSON.stringify(userSession))
          setSessionRole('user')
          setSessionUser(userSession)
          return
        }

        if (adminSession?.role === 'admin') {
          setSessionRole('admin')
          setSessionUser(adminSession)
          return
        }

        // ✅ Cookie failed — try localStorage fallback (cross-domain OAuth)
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
      } catch {
        // ignore
      }

      if (!active) return
      setSessionRole(null)
      setSessionUser(null)
    }

    loadSession().finally(() => {
      if (active) setLoading(false)
    })

    const handleExpiry = () => {
      if (!active) return
      // ✅ Clear localStorage on logout/expiry
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
