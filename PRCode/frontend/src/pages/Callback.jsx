import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMe } from '../api/client'

export default function Callback() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('Processing...')

  useEffect(() => {
    let timerId
    let active = true
    const params = new URLSearchParams(window.location.search)
    const installationId = params.get('installation_id')
    const error          = params.get('error')

    if (error) {
      setStatus('GitHub login failed. Redirecting...')
      timerId = setTimeout(() => navigate('/login'), 2000)
      return () => {
        if (timerId) clearTimeout(timerId)
      }
    }

    if (installationId) {
      // GitHub App installation callback
      localStorage.setItem('prguard_installation_id', installationId)
      setStatus('App installed! Redirecting...')
      timerId = setTimeout(() => navigate('/dashboard'), 1500)
      return () => {
        if (timerId) clearTimeout(timerId)
      }
    }

    const resolveSession = async () => {
      try {
        const session = await getMe()
        if (!active) return

        if (!session) {
          setStatus('Session not found. Redirecting...')
          timerId = setTimeout(() => navigate('/login', { replace: true }), 1200)
          return
        }

        if (session.role !== 'user') {
          setStatus('Admin accounts must use email login. Redirecting...')
          timerId = setTimeout(() => navigate('/admin/login?reason=admin_local_login_required', { replace: true }), 600)
          return
        }

        setStatus('Login successful! Redirecting...')
        timerId = setTimeout(() => navigate('/dashboard', { replace: true }), 600)
      } catch {
        if (!active) return
        setStatus('Could not verify session. Redirecting...')
        timerId = setTimeout(() => navigate('/login', { replace: true }), 1200)
      }
    }

    resolveSession()

    return () => {
      active = false
      if (timerId) clearTimeout(timerId)
    }
  }, [navigate])

  return (
    <main className="min-h-screen flex items-center justify-center"
      style={{ background: '#0d0f12' }}>
      <div className="text-center">
        <div className="w-12 h-12 border-2 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto mb-4"/>
        <p style={{ color: '#e8e4d9', fontWeight: 500 }}>PRGuard</p>
        <p style={{ color: '#6b7280', fontSize: 14, marginTop: 6 }}>{status}</p>
      </div>
    </main>
  )
}