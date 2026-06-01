import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeStep } from '../../../../test/fixtures'
import { StepErrorSummaryCard } from './StepErrorSummaryCard'

describe('StepErrorSummaryCard', () => {
  it('renders a muted zero-error summary and does not expand', () => {
    render(
      <StepErrorSummaryCard
        steps={[makeStep({ step_id: 1, status: 'SUCCESS' })]}
        selectedStepId={null}
        onSelectStep={vi.fn()}
      />,
    )

    const summary = screen.getByRole('button', { name: /step errors: 0/i })
    expect(summary).toBeDisabled()
    expect(summary).toHaveClass('text-slate-500')
  })

  it('turns red, expands, and selects errored steps newest-first', () => {
    const onSelectStep = vi.fn()
    render(
      <StepErrorSummaryCard
        steps={[
          makeStep({ step_id: 1, status: 'ERROR', function_name: 'first_error' }),
          makeStep({ step_id: 3, status: 'ERROR', function_name: 'latest_error' }),
          makeStep({ step_id: 2, status: 'SUCCESS' }),
        ]}
        selectedStepId={null}
        onSelectStep={onSelectStep}
      />,
    )

    const summary = screen.getByRole('button', { name: /step errors: 2/i })
    expect(summary).not.toBeDisabled()
    expect(summary).toHaveClass('text-red-200')

    fireEvent.click(summary)

    const errorButtons = screen.getAllByRole('button', { name: /step #/i })
    expect(errorButtons[0]).toHaveTextContent('step #3')
    expect(errorButtons[1]).toHaveTextContent('step #1')

    fireEvent.click(errorButtons[0])
    expect(onSelectStep).toHaveBeenCalledWith(3)
  })
})
