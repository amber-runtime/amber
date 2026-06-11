import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthGate, authRedirectUri } from './auth'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

const authConfig = {
  enabled: true,
  domain: 'https://example.auth.us-west-2.amazoncognito.com',
  issuer: 'https://cognito-idp.us-west-2.amazonaws.com/us-west-2_test',
  client_id: 'dashboard-client',
  region: 'us-west-2',
  user_pool_id: 'us-west-2_test',
}

function installStorage(name: 'localStorage' | 'sessionStorage') {
  const store = new Map<string, string>()
  Object.defineProperty(window, name, {
    configurable: true,
    value: {
      getItem: vi.fn((key: string) => store.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store.set(key, value)
      }),
      removeItem: vi.fn((key: string) => {
        store.delete(key)
      }),
    },
  })
}

describe('dashboard auth routing', () => {
  beforeEach(() => {
    installStorage('localStorage')
    installStorage('sessionStorage')
    globalThis.fetch = vi.fn()
  })

  it('uses the admin base path for hosted-ui redirects', () => {
    expect(authRedirectUri()).toBe('http://localhost:3000/admin/')
  })

  it('renders children when auth is disabled', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ...authConfig, enabled: false }))

    render(
      <AuthGate>
        <div>Dashboard content</div>
      </AuthGate>,
    )

    expect(await screen.findByText('Dashboard content')).toBeInTheDocument()
  })

  it('starts Cognito login when auth is enabled and no token exists', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(authConfig))

    render(
      <AuthGate>
        <div>Dashboard content</div>
      </AuthGate>,
    )

    await waitFor(() => {
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith(
        'amber.dashboard.returnTo',
        expect.any(String),
      )
    })
    expect(window.sessionStorage.setItem).toHaveBeenCalledWith(
      'amber.dashboard.pkceVerifier',
      expect.any(String),
    )
    expect(window.sessionStorage.setItem).toHaveBeenCalledWith(
      'amber.dashboard.oauthState',
      expect.any(String),
    )
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })

  it('renders a configuration error instead of redirecting when auth config fails', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('{"detail":"Dashboard auth is required but Cognito config is incomplete."}', {
        status: 503,
        statusText: 'Service Unavailable',
      }),
    )

    render(
      <AuthGate>
        <div>Dashboard content</div>
      </AuthGate>,
    )

    expect(await screen.findByText('Dashboard auth is misconfigured')).toBeInTheDocument()
    expect(screen.getByText(/Dashboard auth is required/)).toBeInTheDocument()
    expect(window.sessionStorage.setItem).not.toHaveBeenCalled()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })
})
