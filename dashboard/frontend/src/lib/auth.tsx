import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/admin/api'
const CONFIGURED_BASE = (import.meta.env.VITE_BASE_PATH as string | undefined) ?? import.meta.env.BASE_URL
const APP_BASE = CONFIGURED_BASE && CONFIGURED_BASE !== '/' ? CONFIGURED_BASE : '/admin/'

const ACCESS_TOKEN_KEY = 'amber.dashboard.accessToken'
const ACCESS_TOKEN_EXPIRES_KEY = 'amber.dashboard.accessTokenExpiresAt'
const ID_TOKEN_KEY = 'amber.dashboard.idToken'
const CODE_VERIFIER_KEY = 'amber.dashboard.pkceVerifier'
const STATE_KEY = 'amber.dashboard.oauthState'
const RETURN_TO_KEY = 'amber.dashboard.returnTo'

export interface AuthConfig {
  enabled: boolean
  domain: string
  issuer: string
  client_id: string
  region: string
  user_pool_id: string
}

interface AuthContextValue {
  authenticated: boolean
  logout: () => void
}

const AuthContext = createContext<AuthContextValue>({
  authenticated: false,
  logout: () => undefined,
})

export function useAuth() {
  return useContext(AuthContext)
}

export function getAccessToken(): string | null {
  const token = window.localStorage.getItem(ACCESS_TOKEN_KEY)
  const expiresAt = Number(window.localStorage.getItem(ACCESS_TOKEN_EXPIRES_KEY) ?? '0')
  if (!token || !Number.isFinite(expiresAt) || expiresAt <= Date.now() + 30_000) {
    return null
  }
  return token
}

export function getAuthorizationHeader(): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${API_BASE}/auth/config`)
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text().catch(() => res.statusText)}`)
  }
  return res.json() as Promise<AuthConfig>
}

function randomString(): string {
  const bytes = new Uint8Array(32)
  window.crypto.getRandomValues(bytes)
  return base64Url(bytes)
}

function base64Url(bytes: Uint8Array): string {
  let raw = ''
  bytes.forEach((byte) => {
    raw += String.fromCharCode(byte)
  })
  return window.btoa(raw).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function sha256(value: string): Promise<Uint8Array> {
  const data = new TextEncoder().encode(value)
  const digest = await window.crypto.subtle.digest('SHA-256', data)
  return new Uint8Array(digest)
}

export function authRedirectUri(): string {
  return new URL(APP_BASE, window.location.origin).toString()
}

export async function beginLogin(config: AuthConfig): Promise<void> {
  const verifier = randomString()
  const state = randomString()
  const challenge = base64Url(await sha256(verifier))

  window.sessionStorage.setItem(CODE_VERIFIER_KEY, verifier)
  window.sessionStorage.setItem(STATE_KEY, state)
  window.sessionStorage.setItem(
    RETURN_TO_KEY,
    `${window.location.pathname}${window.location.search}${window.location.hash}` || '/',
  )

  const params = new URLSearchParams({
    client_id: config.client_id,
    code_challenge: challenge,
    code_challenge_method: 'S256',
    redirect_uri: authRedirectUri(),
    response_type: 'code',
    scope: 'openid email profile',
    state,
  })
  window.location.assign(`${config.domain}/oauth2/authorize?${params.toString()}`)
}

export async function handleAuthCallback(config: AuthConfig): Promise<boolean> {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const state = params.get('state')
  if (!code) return false

  const expectedState = window.sessionStorage.getItem(STATE_KEY)
  const verifier = window.sessionStorage.getItem(CODE_VERIFIER_KEY)
  if (!state || state !== expectedState || !verifier) {
    throw new Error('Invalid login response')
  }

  const body = new URLSearchParams({
    client_id: config.client_id,
    code,
    code_verifier: verifier,
    grant_type: 'authorization_code',
    redirect_uri: authRedirectUri(),
  })
  const res = await fetch(`${config.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text().catch(() => res.statusText)}`)
  }

  const payload = (await res.json()) as {
    access_token: string
    expires_in?: number
    id_token?: string
  }
  window.localStorage.setItem(ACCESS_TOKEN_KEY, payload.access_token)
  window.localStorage.setItem(
    ACCESS_TOKEN_EXPIRES_KEY,
    String(Date.now() + (payload.expires_in ?? 3600) * 1000),
  )
  if (payload.id_token) window.localStorage.setItem(ID_TOKEN_KEY, payload.id_token)

  window.sessionStorage.removeItem(CODE_VERIFIER_KEY)
  window.sessionStorage.removeItem(STATE_KEY)
  const returnTo = window.sessionStorage.getItem(RETURN_TO_KEY) || '/'
  window.sessionStorage.removeItem(RETURN_TO_KEY)
  window.history.replaceState({}, '', returnTo)
  return true
}

function clearSession() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY)
  window.localStorage.removeItem(ACCESS_TOKEN_EXPIRES_KEY)
  window.localStorage.removeItem(ID_TOKEN_KEY)
  window.sessionStorage.removeItem(CODE_VERIFIER_KEY)
  window.sessionStorage.removeItem(STATE_KEY)
  window.sessionStorage.removeItem(RETURN_TO_KEY)
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      const nextConfig = await fetchAuthConfig()
      if (cancelled) return
      setConfig(nextConfig)
      if (!nextConfig.enabled) {
        setAuthenticated(true)
        setLoading(false)
        return
      }
      await handleAuthCallback(nextConfig)
      if (cancelled) return
      if (getAccessToken()) {
        setAuthenticated(true)
        setLoading(false)
        return
      }
      await beginLogin(nextConfig)
    }

    load().catch((error) => {
      console.error('Dashboard auth failed:', error)
      if (!cancelled) {
        setError(error instanceof Error ? error.message : String(error))
        setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      authenticated,
      logout: () => {
        clearSession()
        if (config?.enabled) {
          const params = new URLSearchParams({
            client_id: config.client_id,
            logout_uri: authRedirectUri(),
          })
          window.location.assign(`${config.domain}/logout?${params.toString()}`)
        } else {
          window.location.assign(authRedirectUri())
        }
      },
    }),
    [authenticated, config],
  )

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 grid place-items-center">
        <span className="text-sm text-slate-400">Loading...</span>
      </div>
    )
  }

  if (!authenticated) {
    if (error) {
      return (
        <div className="min-h-screen bg-slate-950 text-slate-100 grid place-items-center px-6">
          <div className="max-w-md rounded border border-red-500/50 bg-red-950/20 p-5">
            <h1 className="text-base font-semibold text-red-100">Dashboard auth is misconfigured</h1>
            <p className="mt-2 text-sm text-red-200/80">{error}</p>
          </div>
        </div>
      )
    }
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 grid place-items-center">
        <button
          type="button"
          className="rounded border border-amber-500/60 px-4 py-2 text-sm font-medium text-amber-200 hover:bg-amber-500/10"
          onClick={() => config && beginLogin(config)}
        >
          Sign in
        </button>
      </div>
    )
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
