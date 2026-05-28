import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkflowDetail, WorkflowSummary } from '../../lib/types'
import { makeDetail, makeStep } from '../../test/fixtures'
import { WorkflowListPage } from './WorkflowListPage'
import { MemoryRouter } from 'react-router-dom'

const navigateMock = vi.hoisted(() => vi.fn())
const contextMock = vi.hoisted(() => ({
  workflows: [] as WorkflowSummary[],
  workflowDetails: {} as Record<string, WorkflowDetail>,
  loading: false,
  loadingMore: false,
  hasMore: false,
  error: null as string | null,
  refresh: vi.fn(),
  loadMore: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../../lib/workflowContext', () => ({
  useWorkflows: () => contextMock,
}))

function workflow(overrides: Partial<WorkflowSummary> = {}): WorkflowSummary {
  return {
    workflow_id: 'wf-1',
    name: 'research-assistant',
    status: 'SUCCESS',
    created_at: 1_000,
    completed_at: 5_000,
    recovery_attempts: 1,
    attempts: 1,
    recoveries: 0,
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowListPage />
    </MemoryRouter>,
  )
}

describe('WorkflowListPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    contextMock.workflows = []
    contextMock.workflowDetails = {}
    contextMock.loading = false
    contextMock.loadingMore = false
    contextMock.hasMore = false
    contextMock.error = null
    contextMock.refresh.mockReset()
    contextMock.loadMore.mockReset()
  })

  it('renders rows and updates pending durations from the shared live clock', () => {
    vi.useFakeTimers()
    vi.setSystemTime(4_000)
    contextMock.workflows = [
      workflow({
        workflow_id: 'wf-pending',
        name: 'travel-concierge',
        status: 'PENDING',
        created_at: 1_000,
        completed_at: 1_000,
      }),
    ]

    renderPage()

    expect(screen.getByText('Travel Concierge')).toBeInTheDocument()
    expect(screen.getByText('3.0s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1_000)
    })

    expect(screen.getByText('4.0s')).toBeInTheDocument()
  })

  it('uses derived display status for counts and status filtering', async () => {
    const user = userEvent.setup()
    contextMock.workflows = [
      workflow({ workflow_id: 'wf-success', status: 'SUCCESS', name: 'done-agent' }),
      workflow({ workflow_id: 'wf-pending', status: 'PENDING', name: 'running-agent' }),
      workflow({ workflow_id: 'wf-derived-error', status: 'PENDING', name: 'derived-error' }),
    ]
    contextMock.workflowDetails = {
      'wf-derived-error': makeDetail({
        workflow: { workflow_id: 'wf-derived-error', status: 'PENDING' },
        steps: [
          makeStep({
            status: 'ERROR',
            error_message: 'tool exploded',
          }),
        ],
      }),
    }

    renderPage()

    expect(screen.getByRole('button', { name: 'All (3)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Completed (1)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pending (1)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Errored (1)' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Errored (1)' }))

    expect(screen.getByText('Derived Error')).toBeInTheDocument()
    expect(screen.queryByText('Running Agent')).not.toBeInTheDocument()
    expect(screen.getByText('Error')).toBeInTheDocument()
  })

  it('filters by search and navigates when a row is clicked', async () => {
    const user = userEvent.setup()
    contextMock.workflows = [
      workflow({ workflow_id: 'wf-alpha-123', name: 'alpha-agent' }),
      workflow({ workflow_id: 'wf-beta-456', name: 'beta-agent' }),
    ]

    renderPage()

    await user.type(screen.getByPlaceholderText('Search by name or ID...'), 'beta')

    expect(screen.getByText('Beta Agent')).toBeInTheDocument()
    expect(screen.queryByText('Alpha Agent')).not.toBeInTheDocument()

    await user.click(screen.getByText('Beta Agent'))

    expect(navigateMock).toHaveBeenCalledWith('/workflows/wf-beta-456')
  })

  it('shows loading, empty, and error states and refreshes on request', () => {
    contextMock.loading = true
    const { rerender } = renderPage()
    expect(screen.getByText('Loading workflows…')).toBeInTheDocument()

    contextMock.loading = false
    contextMock.workflows = []
    rerender(
      <MemoryRouter>
        <WorkflowListPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('No workflows yet.')).toBeInTheDocument()

    contextMock.error = 'backend down'
    rerender(
      <MemoryRouter>
        <WorkflowListPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('Failed to load workflows')).toBeInTheDocument()
    expect(screen.getByText('backend down')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(contextMock.refresh).toHaveBeenCalled()
  })

  it('refresh icon calls refresh', () => {
    renderPage()

    fireEvent.click(screen.getByTitle('Refresh'))

    expect(contextMock.refresh).toHaveBeenCalled()
  })
})
