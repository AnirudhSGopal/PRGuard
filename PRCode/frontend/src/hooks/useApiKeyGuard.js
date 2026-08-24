import { useState, useEffect } from 'react'
import { getApiKeyStatus, normalizeApiKeyStatus } from '../api/client'

export const useApiKeyGuard = () => {
  const [hasKey, setHasKey] = useState(false)
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    let mounted = true
    const checkKey = async () => {
      try {
        const status = normalizeApiKeyStatus(await getApiKeyStatus())
        if (mounted) {
          setHasKey(Boolean(status.has_any_key))
        }
      } catch (err) {
        // Log the error but don't immediately lock the user out if we previously had a key.
        // This prevents the popup from flashing on temporary 401/500 errors.
        console.warn('[useApiKeyGuard] Failed to check API key status:', err)
        
        // Only set to false if we haven't loaded anything yet (initial load failure).
        if (loading && mounted) {
          setHasKey(false)
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    checkKey()
    
    // Poll backend status to keep chat guard in sync with settings panel changes.
    const interval = setInterval(checkKey, 8000)
    window.addEventListener('prguard:api-keys-updated', checkKey)
    
    return () => {
      mounted = false
      clearInterval(interval)
      window.removeEventListener('prguard:api-keys-updated', checkKey)
    }
  }, [])

  return { hasKey, loading }
}
