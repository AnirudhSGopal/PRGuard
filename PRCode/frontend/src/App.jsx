import React, { useState, useEffect, createContext } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Callback from './pages/Callback'
import NotFound from './pages/NotFound'
import AdminLogin from './pages/AdminLogin'
import AdminDashboard from './pages/AdminDashboard'
import { useSession } from './hooks/useSession'

export const ThemeContext = createContext('dark')

function LoadingScreen() {
  return <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0d0f12', color: '#6b7280' }}>Loading...</div>
}

function SessionBootstrapRoute() {
  const { loading, isAdmin, isUser } = useSession()

  if (loading) return <LoadingScreen />
  if (isUser) return <Navigate to="/dashboard" replace />
  if (isAdmin) return <Navigate to="/admin/dashboard" replace />
  return <Landing />
}

function UserRoute({ children }) {
  const { loading, isUser } = useSession()

  if (loading) return <LoadingScreen />
  if (!isUser) return <Navigate to="/login" replace />
  return children
}

function AdminRoute({ children }) {
  const { loading, isAdmin } = useSession()

  if (loading) return <LoadingScreen />
  if (!isAdmin) return <Navigate to="/admin/login" replace />
  return children
}

function App() {
  const [theme, setTheme] = useState(() =>
    localStorage.getItem('prguard-theme') || 'dark'
  )

  useEffect(() => {
    document.body.className = `theme-${theme}`
    localStorage.setItem('prguard-theme', theme)
  }, [theme])

  const toggleTheme = () =>
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      <BrowserRouter>
        <Routes>
          <Route path="/"                element={<SessionBootstrapRoute />} />
          <Route path="/landing"         element={<Navigate to="/" replace />} />
          <Route path="/login"           element={<Login />} />
          <Route path="/signup"          element={<Signup />} />
          <Route path="/dashboard"       element={<UserRoute><Dashboard /></UserRoute>} />
          <Route path="/admin/login"     element={<AdminLogin />} />
          <Route path="/admin/dashboard" element={<AdminRoute><AdminDashboard /></AdminRoute>} />
          <Route path="/auth/callback"   element={<Callback />} />
          <Route path="*"                element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </ThemeContext.Provider>
  )
}

export default App