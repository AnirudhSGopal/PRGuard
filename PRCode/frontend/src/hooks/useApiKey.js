import { useEffect, useState } from 'react'
import { getApiKeyStatus } from '../api/client'

/**
 * Hook to manage and persist API key state across the app.
 * Loads from localStorage and backend on mount, and syncs with server.
 */
export const useApiKey = () => {
  const [apiKeyStatus, setApiKeyStatus] = useState(null)
  const [hasKey, setHasKey] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    const loadApiKeyStatus = async () => {
      try {
        const status = await getApiKeyStatus()
        if (!active) return
        setApiKeyStatus(status)
        setHasKey(Boolean(status?.has_any_key))
        setError(null)
      } catch (err) {
        if (!active) return
        console.error('[useApiKey] Failed to load API key status:', err)
        setError('Failed to load API key status')
        setHasKey(false)
      } finally {
        if (active) setLoading(false)
      }
    }

    loadApiKeyStatus()

    return () => {
      active = false
    }
  }, [])

  const refresh = async () => {
    setLoading(true)
    try {
      const status = await getApiKeyStatus()
      setApiKeyStatus(status)
      setHasKey(Boolean(status?.has_any_key))
      setError(null)
    } catch (err) {
      console.error('[useApiKey] Failed to refresh API key status:', err)
      setError('Failed to refresh API key status')
      setHasKey(false)
    } finally {
      setLoading(false)
    }
  }

  return {
    apiKeyStatus,
    hasKey,
    loading,
    error,
    refresh,
  }
}
