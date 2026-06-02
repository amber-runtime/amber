import { beforeEach, describe, expect, it, vi } from 'vitest'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

async function importApi() {
  vi.resetModules()
  vi.stubEnv('VITE_API_BASE_URL', '/api')
  return import('./api')
}

describe('dashboard api client', () => {
  beforeEach(() => {
    vi.unstubAllEnvs()
    globalThis.fetch = vi.fn()
  })

  it('maps workflow list pagination and recovery attempts', async () => {
    const api = await importApi()
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        workflows: [
          {
            workflow_id: 'wf-1',
            name: 'research-assistant',
            status: 'SUCCESS',
            created_at: 1_000,
            completed_at: 3_000,
            recovery_attempts: 3,
          },
        ],
        has_more: true,
      }),
    )

    await expect(api.fetchWorkflows({ limit: 10, offset: 20 })).resolves.toEqual({
      workflows: [
        expect.objectContaining({
          workflow_id: 'wf-1',
          attempts: 3,
          recoveries: 2,
        }),
      ],
      hasMore: true,
    })
    expect(fetch).toHaveBeenCalledWith('/api/workflows?limit=10&offset=20')
  })

  it('maps workflow detail and encodes workflow ids', async () => {
    const api = await importApi()
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        workflow: {
          workflow_id: 'wf/one two',
          name: 'research-assistant',
          status: 'PENDING',
          created_at: 1_000,
          updated_at: 2_000,
          recovery_attempts: null,
          output: null,
        },
        steps: [],
        events: [],
      }),
    )

    await expect(api.fetchWorkflowDetail('wf/one two')).resolves.toEqual({
      workflow: expect.objectContaining({
        workflow_id: 'wf/one two',
        attempts: null,
        recoveries: 0,
      }),
      steps: [],
    })
    expect(fetch).toHaveBeenCalledWith('/api/workflows/wf%2Fone%20two')
  })

  it('maps queued workflow pages and queue-name query params', async () => {
    const api = await importApi()
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        workflows: [
          {
            workflow_id: 'wf-queued',
            name: 'queued-agent',
            status: 'ENQUEUED',
            created_at: 1_000,
            queue_name: 'priority queue',
            recovery_attempts: 2,
          },
        ],
        has_more: false,
      }),
    )

    await expect(
      api.fetchQueuedWorkflows({ limit: 5, offset: 10, queueName: 'priority queue' }),
    ).resolves.toEqual({
      workflows: [
        expect.objectContaining({
          workflow_id: 'wf-queued',
          attempts: 2,
        }),
      ],
      hasMore: false,
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/queued-workflows?limit=5&offset=10&queue_name=priority+queue',
    )
  })

  it('posts resume and cancel requests with encoded workflow ids', async () => {
    const api = await importApi()
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({}))
      .mockResolvedValueOnce(jsonResponse({}))

    await api.resumeWorkflow('wf/one')
    await api.cancelWorkflow('wf/two')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/workflows/wf%2Fone/resume', {
      method: 'POST',
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/workflows/wf%2Ftwo/cancel', {
      method: 'POST',
    })
  })

  it('throws useful errors for non-ok responses', async () => {
    const api = await importApi()
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('backend unavailable', { status: 503, statusText: 'Unavailable' }),
    )

    await expect(api.fetchWorkflows()).rejects.toThrow('HTTP 503: backend unavailable')
  })
})
