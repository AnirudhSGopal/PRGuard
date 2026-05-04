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

        if (userSession?.login) {
          setSessionRole('user')
          setSessionUser(userSession)
          return
        }

        if (adminSession?.role === 'admin') {
          setSessionRole('admin')
          setSessionUser(adminSession)
          return
        }
      } catch {
        // Ignore and fall through to the unauthenticated state.
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