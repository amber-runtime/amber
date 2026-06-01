import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ForkSuccessModal } from './ForkSuccessModal'

describe('ForkSuccessModal', () => {
  it('renders the updated copy', () => {
    render(
      <ForkSuccessModal
        workflowId="wf-2"
        onClose={vi.fn()}
        onViewWorkflow={vi.fn()}
      />,
    )

    expect(screen.getByText('Workflow forked')).toBeInTheDocument()
    expect(
      screen.getByText(
        'A new workflow was created from this step and is now running. This workflow was not changed.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View forked workflow' })).toBeInTheDocument()
  })

  it('closes on secondary and close actions, and forwards the workflow id to view action', () => {
    const onClose = vi.fn()
    const onViewWorkflow = vi.fn()

    render(
      <ForkSuccessModal
        workflowId="wf-2"
        onClose={onClose}
        onViewWorkflow={onViewWorkflow}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Stay here' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.click(screen.getByRole('button', { name: 'View forked workflow' }))

    expect(onClose).toHaveBeenCalledTimes(2)
    expect(onViewWorkflow).toHaveBeenCalledWith('wf-2')
  })
})
