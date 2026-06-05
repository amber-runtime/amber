import { describe, expect, it } from 'vitest'

import { authRedirectUri } from './auth'

describe('dashboard auth routing', () => {
  it('uses the admin base path for hosted-ui redirects', () => {
    expect(authRedirectUri()).toBe('http://localhost:3000/admin/')
  })
})
