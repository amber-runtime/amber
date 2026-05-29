import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { setPricing } from '../../lib/pricingStore'
import { makeDetail, makeStep, makeWorkflow } from '../../test/fixtures'
import { renderWithRoute } from '../../test/render'
import { WorkflowListPage } from '../list/WorkflowListPage'
import { WorkflowDetailPage } from './WorkflowDetailPage'

const apiMocks = vi.hoisted(() => ({
  fetchWorkflowDetail: vi.fn(),
  resumeWorkflow: vi.fn(),
  cancelWorkflow: vi.fn(),
  forkWorkflow: vi.fn(),
}))

const contextMocks = vi.hoisted(() => ({
  workflowDetails: {} as Record<string, ReturnType<typeof makeDetail>>,
  setDetail: vi.fn(),
}))

vi.mock('../../lib/api', () => apiMocks)
vi.mock('../../lib/workflowContext', () => ({
  useWorkflows: () => ({
    workflowDetails: contextMocks.workflowDetails,
    setDetail: contextMocks.setDetail,
  }),
}))

function renderDetailPage() {
  return renderWithRoute(<WorkflowDetailPage />, {
    route: '/workflows/wf-1',
    path: '/workflows/:id',
  })
}

describe('WorkflowDetailPage', () => {
  beforeEach(() => {
    setPricing({}, null)
    contextMocks.workflowDetails = {}
    contextMocks.setDetail.mockReset()
  })

  it('shows initial loading while the workflow detail request is in flight', () => {
    apiMocks.fetchWorkflowDetail.mockReturnValue(new Promise(() => undefined))

    renderDetailPage()

    expect(screen.getByText('Loading workflow…')).toBeInTheDocument()
    expect(apiMocks.fetchWorkflowDetail).toHaveBeenCalledWith('wf-1')
  })

  it('shows initial fetch failure and retries on request', async () => {
    const user = userEvent.setup()
    apiMocks.fetchWorkflowDetail
      .mockRejectedValueOnce(new Error('backend unavailable'))
      .mockResolvedValueOnce(makeDetail())

    renderDetailPage()

    expect(await screen.findByText('Failed to load workflow.')).toBeInTheDocument()
    expect(screen.getByText('backend unavailable')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /retry/i }))

    await waitFor(() => expect(apiMocks.fetchWorkflowDetail).toHaveBeenCalledTimes(2))
    expect(contextMocks.setDetail).toHaveBeenCalledWith('wf-1', expect.any(Object))
  })

  it('keeps stale data visible and shows a refresh failure banner', async () => {
    contextMocks.workflowDetails = {
      'wf-1': makeDetail({ workflow: { workflow_id: 'wf-1', status: 'PENDING' } }),
    }
    apiMocks.fetchWorkflowDetail.mockRejectedValue(new Error('timeout'))

    renderDetailPage()

    expect(screen.getByRole('heading', { level: 1, name: 'Research Assistant' })).toBeInTheDocument()
    expect(await screen.findByText('Failed to refresh. Showing last known data.')).toBeInTheDocument()
    expect(screen.getByText('timeout')).toBeInTheDocument()
  })

  it('shows red row downtime while stale pending data cannot refresh and closes it after recovery', async () => {
    const now = vi.spyOn(Date, 'now').mockReturnValue(6_000)
    const firstStep = makeStep({
      step_id: 1,
      started_at_epoch_ms: 500,
      completed_at_epoch_ms: 900,
    })
    const lastStep = makeStep({
      step_id: 2,
      started_at_epoch_ms: 1_000,
      completed_at_epoch_ms: null,
      display_completed_at_epoch_ms: undefined as unknown as null,
      duration_ms: null,
      display_duration_ms: undefined as unknown as null,
    })
    const recoveredDetail = makeDetail({
      workflow: {
        workflow_id: 'wf-1',
        status: 'PENDING',
        created_at: 0,
        updated_at: 0,
      },
      steps: [firstStep, lastStep],
    })
    contextMocks.workflowDetails = { 'wf-1': recoveredDetail }
    apiMocks.fetchWorkflowDetail
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(recoveredDetail)

    renderDetailPage()

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByText('Failed to refresh. Showing last known data.')).toBeInTheDocument()
    expect(screen.getAllByTestId('step-gantt-bar')).toHaveLength(2)
    expect(screen.getAllByTestId('downtime-gantt-bar')).toHaveLength(1)
    expect(screen.getByTestId('downtime-gantt-bar')).toHaveClass('bg-red-500/85')

    now.mockReturnValue(9_000)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /refresh now/i }))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.queryByText('Failed to refresh. Showing last known data.')).not.toBeInTheDocument()
    expect(contextMocks.setDetail).toHaveBeenCalledWith('wf-1', recoveredDetail)
  })

  it('shows red row downtime for an errored workflow', async () => {
    contextMocks.workflowDetails = {
      'wf-1': makeDetail({
        workflow: {
          workflow_id: 'wf-1',
          status: 'ERROR',
          created_at: 0,
          updated_at: 4_000,
        },
        steps: [
          makeStep({
            step_id: 1,
            status: 'ERROR',
            started_at_epoch_ms: 2_000,
            completed_at_epoch_ms: 2_500,
          }),
        ],
      }),
    }
    apiMocks.fetchWorkflowDetail.mockResolvedValue(contextMocks.workflowDetails['wf-1'])

    renderDetailPage()

    expect(screen.getByTestId('downtime-gantt-bar')).toHaveClass('bg-red-500/85')
    expect(screen.queryByText('running…')).not.toBeInTheDocument()
  })

  it('shows the waiting state and manual refresh for pending workflows with no steps', () => {
    contextMocks.workflowDetails = {
      'wf-1': makeDetail({
        workflow: { workflow_id: 'wf-1', status: 'PENDING' },
        steps: [],
      }),
    }
    apiMocks.fetchWorkflowDetail.mockResolvedValue(contextMocks.workflowDetails['wf-1'])

    renderDetailPage()

    expect(screen.getByText('Waiting for first step…')).toBeInTheDocument()
    expect(screen.getByText('Polling every 2 seconds')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /refresh now/i })).toBeInTheDocument()
  })

  it('polls non-terminal workflows', async () => {
    vi.useFakeTimers()
    contextMocks.workflowDetails = {
      'wf-1': makeDetail({ workflow: { workflow_id: 'wf-1', status: 'PENDING' } }),
    }
    apiMocks.fetchWorkflowDetail.mockResolvedValue(contextMocks.workflowDetails['wf-1'])

    renderDetailPage()

    expect(apiMocks.fetchWorkflowDetail).toHaveBeenCalledTimes(1)

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    await act(async () => {
      vi.advanceTimersByTime(2_000)
      await Promise.resolve()
    })

    expect(apiMocks.fetchWorkflowDetail).toHaveBeenCalledTimes(2)
  })

  it('does not poll terminal workflows after the initial load', async () => {
    vi.useFakeTimers()
    contextMocks.workflowDetails = {
      'wf-1': {
        workflow: makeWorkflow({ workflow_id: 'wf-1', status: 'SUCCESS' }),
        steps: [],
      },
    }
    apiMocks.fetchWorkflowDetail.mockResolvedValue(contextMocks.workflowDetails['wf-1'])

    renderDetailPage()

    expect(apiMocks.fetchWorkflowDetail).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(10_000)
      await Promise.resolve()
    })

    expect(apiMocks.fetchWorkflowDetail).toHaveBeenCalledTimes(1)
  })

  it('navigates to the workflows list page instead of history back', async () => {
    contextMocks.workflowDetails = {
      'wf-1': makeDetail({ workflow: { workflow_id: 'wf-1', status: 'SUCCESS' } }),
    }
    apiMocks.fetchWorkflowDetail.mockResolvedValue(contextMocks.workflowDetails['wf-1'])

    renderWithRoute(
      <Routes>
        <Route path="/" element={<WorkflowListPage />} />
        <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
      </Routes>,
      {
        route: '/workflows/wf-1',
        path: '*',
      },
    )

    await userEvent.click(screen.getByRole('button', { name: /workflows/i }))

    expect(await screen.findByPlaceholderText('Search by name or ID...')).toBeInTheDocument()
  })
})
