import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { DowntimeInterval } from '../../../lib/stepHelpers'
import { makeStep } from '../../../test/fixtures'
import { StepRow } from './StepRow'

const START = 0
const END = 10_000

function renderRow({
  step = makeStep({
    started_at_epoch_ms: 1_000,
    completed_at_epoch_ms: 2_000,
  }),
  workflowIsActive = true,
  downtimeIntervals = [],
  nowMs = END,
}: {
  step?: ReturnType<typeof makeStep>
  workflowIsActive?: boolean
  downtimeIntervals?: DowntimeInterval[]
  nowMs?: number
} = {}) {
  return render(
    <StepRow
      step={step}
      isSelected={false}
      onClick={vi.fn()}
      workflowStart={START}
      workflowEnd={END}
      workflowIsActive={workflowIsActive}
      downtimeIntervals={downtimeIntervals}
      nowMs={nowMs}
    />,
  )
}

describe('StepRow', () => {
  it('renders red downtime segments inside the row gantt track', () => {
    renderRow({
      downtimeIntervals: [{ start: 2_000, end: 6_000, source: 'refresh' }],
    })

    const downtime = screen.getByTestId('downtime-gantt-bar')
    expect(downtime).toHaveStyle({ left: '20%', width: '40%' })
  })

  it('keeps the normal completed work bar while overlaying downtime', () => {
    renderRow({
      downtimeIntervals: [{ start: 3_000, end: 4_000, source: 'error' }],
    })

    expect(screen.getByTestId('step-gantt-bar')).toHaveClass('bg-emerald-500/70')
    expect(screen.getByTestId('downtime-gantt-bar')).toHaveClass('bg-red-500/85')
  })

  it('extends unresolved downtime with the current timeline clock', () => {
    const { rerender } = render(
      <StepRow
        step={makeStep({
          started_at_epoch_ms: 1_000,
          completed_at_epoch_ms: null,
          display_completed_at_epoch_ms: undefined as unknown as null,
          duration_ms: null,
          display_duration_ms: undefined as unknown as null,
        })}
        isSelected={false}
        onClick={vi.fn()}
        workflowStart={START}
        workflowEnd={END}
        workflowIsActive={false}
        downtimeIntervals={[{ start: 2_000, end: null, source: 'refresh' }]}
        nowMs={5_000}
      />,
    )

    expect(screen.getByTestId('downtime-gantt-bar')).toHaveStyle({ width: '30%' })

    rerender(
      <StepRow
        step={makeStep({
          started_at_epoch_ms: 1_000,
          completed_at_epoch_ms: null,
          display_completed_at_epoch_ms: undefined as unknown as null,
          duration_ms: null,
          display_duration_ms: undefined as unknown as null,
        })}
        isSelected={false}
        onClick={vi.fn()}
        workflowStart={START}
        workflowEnd={END}
        workflowIsActive={false}
        downtimeIntervals={[{ start: 2_000, end: null, source: 'refresh' }]}
        nowMs={8_000}
      />,
    )

    expect(screen.getByTestId('downtime-gantt-bar')).toHaveStyle({ width: '60%' })
    expect(screen.queryByText('running…')).not.toBeInTheDocument()
  })
})
