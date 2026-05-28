import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setPricing } from '../../../lib/pricingStore'
import { makeStep, makeToolStep, makeWorkflow } from '../../../test/fixtures'
import { WorkflowHeader } from './WorkflowHeader'

const apiMocks = vi.hoisted(() => ({
  resumeWorkflow: vi.fn(),
  cancelWorkflow: vi.fn(),
}))

const toastMocks = vi.hoisted(() => ({
  showToast: vi.fn(),
}))

vi.mock('../../../lib/api', () => apiMocks)
vi.mock('../../../shared/Toast', () => toastMocks)

describe('WorkflowHeader', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders workflow stats from steps', () => {
    setPricing(
      {
        'gpt-4o-mini': {
          input: 0.00000015,
          output: 0.0000006,
          cache_read: null,
          cache_creation: null,
        },
      },
      null,
    )

    render(
      <WorkflowHeader
        workflow={makeWorkflow({ recovery_attempts: 2, attempts: 2 })}
        steps={[makeStep({ tokens_in: 1_000, tokens_out: 500 }), makeToolStep()]}
        displayStatus="SUCCESS"
      />,
    )

    expect(screen.getByRole('heading', { name: 'Research Assistant' })).toBeInTheDocument()
    expect(screen.getByText('Success')).toBeInTheDocument()
    expect(screen.getByText('Attempts: 2')).toBeInTheDocument()
    expect(screen.getByText(/LLM call/)).toBeInTheDocument()
    expect(screen.getByText(/Tool call/)).toBeInTheDocument()
    expect(screen.getAllByText('1')).toHaveLength(2)
    expect(screen.getByText('1,000 in · 500 out')).toBeInTheDocument()
    expect(screen.getByText('<$0.01')).toBeInTheDocument()
  })

  it('renders pending workflow duration from the live clock', () => {
    vi.useFakeTimers()
    vi.setSystemTime(4_000)

    render(
      <WorkflowHeader
        workflow={makeWorkflow({
          status: 'PENDING',
          created_at: 1_000,
          updated_at: 1_000,
        })}
        steps={[]}
        displayStatus="PENDING"
      />,
    )

    expect(screen.getByText('3.0s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1_000)
    })

    expect(screen.getByText('4.0s')).toBeInTheDocument()
  })

  it('keeps duration visible when created and updated timestamps match', () => {
    render(
      <WorkflowHeader
        workflow={makeWorkflow({
          status: 'SUCCESS',
          created_at: 1_000,
          updated_at: 1_000,
        })}
        steps={[]}
        displayStatus="SUCCESS"
      />,
    )

    expect(screen.getByText('0ms')).toBeInTheDocument()
  })

  it('enables resume only for resumable statuses and cancel only for pending', () => {
    const { rerender } = render(
      <WorkflowHeader
        workflow={makeWorkflow({ status: 'ERROR' })}
        steps={[]}
        displayStatus="ERROR"
      />,
    )
    expect(screen.getByRole('button', { name: /resume/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()

    rerender(
      <WorkflowHeader
        workflow={makeWorkflow({ status: 'CANCELLED' })}
        steps={[]}
        displayStatus="CANCELLED"
      />,
    )
    expect(screen.getByRole('button', { name: /resume/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()

    rerender(
      <WorkflowHeader
        workflow={makeWorkflow({ status: 'PENDING' })}
        steps={[]}
        displayStatus="PENDING"
      />,
    )
    expect(screen.getByRole('button', { name: /resume/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeEnabled()

    rerender(
      <WorkflowHeader
        workflow={makeWorkflow({ status: 'SUCCESS' })}
        steps={[]}
        displayStatus="SUCCESS"
      />,
    )
    expect(screen.getByRole('button', { name: /resume/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
  })

  it('calls resume API, refreshes, and shows success feedback', async () => {
    const user = userEvent.setup()
    const onActionSuccess = vi.fn()
    apiMocks.resumeWorkflow.mockResolvedValue(undefined)

    render(
      <WorkflowHeader
        workflow={makeWorkflow({ workflow_id: 'wf-error', status: 'ERROR' })}
        steps={[]}
        displayStatus="ERROR"
        onActionSuccess={onActionSuccess}
      />,
    )

    await user.click(screen.getByRole('button', { name: /resume/i }))

    await waitFor(() => expect(apiMocks.resumeWorkflow).toHaveBeenCalledWith('wf-error'))
    expect(onActionSuccess).toHaveBeenCalled()
    expect(toastMocks.showToast).toHaveBeenCalledWith('Workflow resumed')
  })

  it('calls cancel API and reports failures through toast feedback', async () => {
    const user = userEvent.setup()
    apiMocks.cancelWorkflow.mockRejectedValue(new Error('network down'))

    render(
      <WorkflowHeader
        workflow={makeWorkflow({ workflow_id: 'wf-pending', status: 'PENDING' })}
        steps={[]}
        displayStatus="PENDING"
      />,
    )

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() => expect(apiMocks.cancelWorkflow).toHaveBeenCalledWith('wf-pending'))
    expect(toastMocks.showToast).toHaveBeenCalledWith('Cancel failed', 'network down')
  })
})
