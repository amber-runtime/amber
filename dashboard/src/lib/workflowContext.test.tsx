import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import type { WorkflowListPage, WorkflowSummary } from './types'
import { WorkflowProvider, useWorkflows } from './workflowContext'

const apiMocks = vi.hoisted(() => ({
  fetchWorkflows: vi.fn(),
}))

vi.mock('./api', () => apiMocks)

function workflow(overrides: Partial<WorkflowSummary> = {}): WorkflowSummary {
  return {
    workflow_id: 'wf-1',
    name: 'research-assistant',
    status: 'SUCCESS',
    created_at: 1_000,
    completed_at: 2_000,
    recovery_attempts: 1,
    attempts: 1,
    recoveries: 0,
    ...overrides,
  }
}

function page(
  workflows: WorkflowSummary[],
  hasMore = false,
): WorkflowListPage {
  return { workflows, hasMore }
}

function Consumer() {
  const ctx = useWorkflows()
  return (
    <div>
      <div data-testid="workflow-ids">
        {ctx.workflows.map((w) => w.workflow_id).join(',')}
      </div>
      <div data-testid="error">{ctx.error ?? ''}</div>
      <div data-testid="loading">{String(ctx.loading)}</div>
      <div data-testid="has-more">{String(ctx.hasMore)}</div>
      <button type="button" onClick={() => void ctx.refresh()}>
        refresh
      </button>
      <button type="button" onClick={() => void ctx.loadMore()}>
        load more
      </button>
    </div>
  )
}

function renderProvider(children: ReactNode = <Consumer />) {
  return render(<WorkflowProvider>{children}</WorkflowProvider>)
}

function setDocumentHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', {
    configurable: true,
    value: hidden,
  })
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('WorkflowProvider', () => {
  beforeEach(() => {
    apiMocks.fetchWorkflows.mockReset()
    setDocumentHidden(false)
  })

  it('loads the first page on mount', async () => {
    apiMocks.fetchWorkflows.mockResolvedValueOnce(page([workflow({ workflow_id: 'wf-1' })]))

    renderProvider()

    await waitFor(() =>
      expect(apiMocks.fetchWorkflows).toHaveBeenCalledWith({ limit: 50, offset: 0 }),
    )
    expect(await screen.findByTestId('workflow-ids')).toHaveTextContent('wf-1')
    expect(screen.getByTestId('loading')).toHaveTextContent('false')
  })

  it('loadMore appends deduped rows and polling refreshes the loaded range', async () => {
    vi.useFakeTimers()
    apiMocks.fetchWorkflows
      .mockResolvedValueOnce(page([workflow({ workflow_id: 'wf-1' })], true))
      .mockResolvedValueOnce(page([
        workflow({ workflow_id: 'wf-1' }),
        workflow({ workflow_id: 'wf-2' }),
      ], true))
      .mockResolvedValueOnce(page([
        workflow({ workflow_id: 'wf-1' }),
        workflow({ workflow_id: 'wf-2' }),
      ], false))

    renderProvider()

    await flushPromises()
    expect(screen.getByTestId('workflow-ids')).toHaveTextContent('wf-1')

    await act(async () => {
      fireEvent.click(screen.getByText('load more'))
      await Promise.resolve()
    })

    expect(apiMocks.fetchWorkflows).toHaveBeenNthCalledWith(2, {
      limit: 50,
      offset: 50,
    })
    expect(screen.getByTestId('workflow-ids')).toHaveTextContent('wf-1,wf-2')

    await act(async () => {
      vi.advanceTimersByTime(5_000)
      await Promise.resolve()
    })

    expect(apiMocks.fetchWorkflows).toHaveBeenNthCalledWith(3, {
      limit: 52,
      offset: 0,
    })
  })

  it('sets errors while preserving existing workflow data', async () => {
    apiMocks.fetchWorkflows
      .mockResolvedValueOnce(page([workflow({ workflow_id: 'wf-existing' })]))
      .mockRejectedValueOnce(new Error('network down'))

    renderProvider()

    await screen.findByText('wf-existing')

    await act(async () => {
      fireEvent.click(screen.getByText('refresh'))
      await Promise.resolve()
    })

    expect(screen.getByTestId('workflow-ids')).toHaveTextContent('wf-existing')
    expect(screen.getByTestId('error')).toHaveTextContent('network down')
  })

  it('pauses polling while hidden and resumes when visible', async () => {
    vi.useFakeTimers()
    apiMocks.fetchWorkflows
      .mockResolvedValueOnce(page([workflow({ workflow_id: 'wf-1' })]))
      .mockResolvedValueOnce(page([workflow({ workflow_id: 'wf-2' })]))

    renderProvider()
    await flushPromises()
    expect(screen.getByTestId('workflow-ids')).toHaveTextContent('wf-1')

    act(() => {
      setDocumentHidden(true)
      fireEvent(document, new Event('visibilitychange'))
      vi.advanceTimersByTime(5_000)
    })

    expect(apiMocks.fetchWorkflows).toHaveBeenCalledTimes(1)

    await act(async () => {
      setDocumentHidden(false)
      fireEvent(document, new Event('visibilitychange'))
      await Promise.resolve()
    })

    expect(apiMocks.fetchWorkflows).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('workflow-ids')).toHaveTextContent('wf-2')
  })
})
