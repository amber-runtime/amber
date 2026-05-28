import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { QueuedWorkflowListPage, QueuedWorkflowSummary } from '../../lib/types'
import { QueuedPage } from './QueuedPage'
import { MemoryRouter } from 'react-router-dom'

const navigateMock = vi.hoisted(() => vi.fn())
const apiMocks = vi.hoisted(() => ({
  fetchQueuedWorkflows: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../../lib/api', () => apiMocks)

function queued(overrides: Partial<QueuedWorkflowSummary> = {}): QueuedWorkflowSummary {
  return {
    workflow_id: 'wf-queued',
    name: 'queued-agent',
    status: 'ENQUEUED',
    created_at: 1_000,
    queue_name: 'default',
    recovery_attempts: 1,
    attempts: 1,
    ...overrides,
  }
}

function page(
  workflows: QueuedWorkflowSummary[],
  hasMore = false,
): QueuedWorkflowListPage {
  return { workflows, hasMore }
}

function setDocumentHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', {
    configurable: true,
    value: hidden,
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <QueuedPage />
    </MemoryRouter>,
  )
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('QueuedPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    apiMocks.fetchQueuedWorkflows.mockReset()
    setDocumentHidden(false)
  })

  it('renders queued workflows, filters search, and navigates to detail', async () => {
    const user = userEvent.setup()
    apiMocks.fetchQueuedWorkflows.mockResolvedValueOnce(
      page([
        queued({ workflow_id: 'wf-alpha', name: 'alpha-agent' }),
        queued({ workflow_id: 'wf-beta', name: 'beta-agent' }),
      ]),
    )

    renderPage()

    expect(await screen.findByText('Alpha Agent')).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('Search by name or ID...'), 'beta')

    expect(screen.getByText('Beta Agent')).toBeInTheDocument()
    expect(screen.queryByText('Alpha Agent')).not.toBeInTheDocument()

    await user.click(screen.getByText('Beta Agent'))

    expect(navigateMock).toHaveBeenCalledWith('/workflows/wf-beta')
  })

  it('shows empty and retry states', async () => {
    apiMocks.fetchQueuedWorkflows
      .mockRejectedValueOnce(new Error('queue backend down'))
      .mockResolvedValueOnce(page([]))

    renderPage()

    expect(await screen.findByText('Failed to load queued workflows')).toBeInTheDocument()
    expect(screen.getByText('queue backend down')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
      await Promise.resolve()
    })

    expect(screen.getByText('No queued workflows.')).toBeInTheDocument()
  })

  it('load-more appends deduped queued rows', async () => {
    apiMocks.fetchQueuedWorkflows
      .mockResolvedValueOnce(page([queued({ workflow_id: 'wf-1' })], true))
      .mockResolvedValueOnce(page([
        queued({ workflow_id: 'wf-1' }),
        queued({ workflow_id: 'wf-2', name: 'second-agent' }),
      ]))

    renderPage()

    expect(await screen.findByText('Queued Agent')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
      await Promise.resolve()
    })

    expect(apiMocks.fetchQueuedWorkflows).toHaveBeenNthCalledWith(2, {
      limit: 50,
      offset: 50,
    })
    expect(screen.getByText('Second Agent')).toBeInTheDocument()
    expect(screen.getAllByText('Queued Agent')).toHaveLength(1)
  })

  it('pauses polling while hidden and resumes when visible', async () => {
    vi.useFakeTimers()
    apiMocks.fetchQueuedWorkflows
      .mockResolvedValueOnce(page([queued({ workflow_id: 'wf-1' })]))
      .mockResolvedValueOnce(page([queued({ workflow_id: 'wf-2', name: 'second-agent' })]))

    renderPage()
    await flushPromises()
    expect(screen.getByText('Queued Agent')).toBeInTheDocument()

    act(() => {
      setDocumentHidden(true)
      fireEvent(document, new Event('visibilitychange'))
      vi.advanceTimersByTime(5_000)
    })

    expect(apiMocks.fetchQueuedWorkflows).toHaveBeenCalledTimes(1)

    await act(async () => {
      setDocumentHidden(false)
      fireEvent(document, new Event('visibilitychange'))
      await Promise.resolve()
    })

    expect(apiMocks.fetchQueuedWorkflows).toHaveBeenCalledTimes(2)
    expect(screen.getByText('Second Agent')).toBeInTheDocument()
  })
})
