import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  const disallowedEnvFiles = [
    '.env',
    '.env.development',
    '.env.production',
    '.env.development.local',
    '.env.production.local',
  ]

  const activeConflicts = disallowedEnvFiles.filter((fileName) =>
    fs.existsSync(path.join(__dirname, fileName))
  )

  if (activeConflicts.length > 0) {
    throw new Error(
      `Only frontend/.env.local is allowed as an active frontend env source. Remove: ${activeConflicts.join(', ')}`
    )
  }

  const env = loadEnv(mode, __dirname, 'VITE_')
  const apiBaseUrlRaw = env.VITE_API_BASE_URL
  const githubClientIdRaw = env.VITE_GITHUB_CLIENT_ID
  const apiBaseUrl = typeof apiBaseUrlRaw === 'string' ? apiBaseUrlRaw.trim() : ''
  const githubClientId = typeof githubClientIdRaw === 'string' ? githubClientIdRaw.trim() : ''

  const isLocalhostTarget = (value) => {
    const normalized = (value || '').toLowerCase()
    return normalized.includes('localhost') || normalized.includes('127.0.0.1')
  }

  if (command === 'build') {
    if (!apiBaseUrl || isLocalhostTarget(apiBaseUrl)) {
      throw new Error(
        'VITE_API_BASE_URL must be set to your deployed ' +
        'backend URL for production build. ' +
        'Current value: ' + apiBaseUrl
      )
    }
    if (!/^https?:\/\//i.test(apiBaseUrl)) {
      throw new Error('VITE_API_BASE_URL must be an absolute URL (http:// or https://).')
    }
    if (!githubClientId) {
      throw new Error('VITE_GITHUB_CLIENT_ID is required for production builds.')
    }
  }

  return {
    plugins: [react()],
  }
})
