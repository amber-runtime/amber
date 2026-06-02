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
      visualActiveStepId={null}
      downtimeIntervals={downtimeIntervals}
      nowMs={nowMs}
    />,
  )
}

describe('StepRow', () => {
  it('ignores downtime overlays in the detail gantt track', () => {
    renderRow({
      downtimeIntervals: [{ start: 2_000, end: 6_000, source: 'refresh' }],
    })

    expect(screen.queryByTestId('downtime-gantt-bar')).not.toBeInTheDocument()
  })

  it('keeps completed work bars green even when downtime metadata exists', () => {
    renderRow({
      downtimeIntervals: [{ start: 3_000, end: 4_000, source: 'error' }],
    })

    expect(screen.getByTestId('step-gantt-bar')).toHaveClass('bg-emerald-500/70')
  })

  it('uses timeline-only timestamps for gantt placement without affecting row duration text', () => {
    renderRow({
      step: makeStep({
        started_at_epoch_ms: 1_000,
        completed_at_epoch_ms: 2_000,
        timeline_started_at_epoch_ms: 4_000,
        timeline_completed_at_epoch_ms: 6_000,
        duration_ms: 1_000,
      }),
      workflowIsActive: false,
    })

    expect(screen.getByTestId('step-gantt-bar')).toHaveStyle({ left: '40%', width: '20%' })
    expect(screen.getByText('1.0s')).toBeInTheDocument()
  })

  it('renders incomplete non-error steps amber instead of red', () => {
    renderRow({
      step: makeStep({
        started_at_epoch_ms: 1_000,
        completed_at_epoch_ms: null,
        display_completed_at_epoch_ms: undefined as unknown as null,
        duration_ms: null,
        display_duration_ms: undefined as unknown as null,
      }),
      workflowIsActive: false,
    })

    expect(screen.getByTestId('step-gantt-bar')).toHaveClass('bg-amber-500/70')
    expect(screen.getByText('running…')).toBeInTheDocument()
  })

  it('renders errored rows as a full red gantt track', () => {
    renderRow({
      step: makeStep({
        status: 'ERROR',
        started_at_epoch_ms: 1_000,
        completed_at_epoch_ms: 1_050,
      }),
      workflowIsActive: false,
    })

    expect(screen.getByTestId('step-gantt-track')).toHaveClass('bg-red-500/80')
    expect(screen.queryByTestId('step-gantt-bar')).not.toBeInTheDocument()
  })
})
