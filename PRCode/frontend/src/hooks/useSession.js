import { useEffect, useState } from 'react'
import { getAdminMe, getMe } from '../api/client'

export const useSession = () => {
  const [loading, setLoading] = useState(true)
  const [session, setSession] = useState(() => {
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
          const currentSession = session
          const merged = { ...userSession }
          if (currentSession?.token && !merged.token) merged.token = currentSession.token
          if (currentSession?.gh_token && !merged.gh_token) merged.gh_token = currentSession.gh_token
          if (currentSession?.github_token && !merged.github_token) merged.github_token = currentSession.github_token
          
          localStorage.setItem('prguard_session', JSON.stringify(merged))
          setSession(merged)
          return
        }

        if (adminSession?.authenticated && adminSession?.role === 'admin') {
          const currentSession = session
          const merged = { ...adminSession }
          if (currentSession?.token && !merged.token) merged.token = currentSession.token

          localStorage.setItem('prguard_session', JSON.stringify(merged))
          setSession(merged)
          return
        }

        // If backend says unauthenticated, clear any stale session
        if (session) {
          localStorage.removeItem('prguard_session')
          setSession(null)
        }

      } catch (err) {
        // On API error, trust localStorage session if it exists
        console.warn('[useSession] API error during session load:', err)
      }
    }

    loadSession().finally(() => {
      if (active) setLoading(false)
    })

    const handleExpiry = () => {
      if (!active) return
      localStorage.removeItem('prguard_session')
      setSession(null)
      setLoading(false)
    }

    window.addEventListener('auth:expired', handleExpiry)
    return () => {
      active = false
      window.removeEventListener('auth:expired', handleExpiry)
    }
  }, [])

  const role = session?.role || null

  return {
    loading,
    sessionRole: role,
    sessionUser: session,
    isAuthenticated: role !== null,
    isAdmin: role === 'admin',
    isUser: role === 'user',
    session,
    setSession,
  }
}
