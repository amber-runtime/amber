import type { ComponentProps } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeStep, makeWorkflow } from '../../../test/fixtures'
import { StepList } from './StepList'

function renderStepList({
  steps,
  workflow = makeWorkflow({
    status: 'PENDING',
    created_at: 0,
    updated_at: 0,
  }),
  resolvedRefreshDowntimes = [],
}: {
  steps: ReturnType<typeof makeStep>[]
  workflow?: ReturnType<typeof makeWorkflow>
  resolvedRefreshDowntimes?: ComponentProps<typeof StepList>['resolvedRefreshDowntimes']
}) {
  return render(
    <StepList
      workflow={workflow}
      steps={steps}
      displayStatus={workflow.status}
      resolvedRefreshDowntimes={resolvedRefreshDowntimes}
      selectedStepId={null}
      onStepClick={vi.fn()}
    />,
  )
}

describe('StepList downtime row anchoring', () => {
  it('does not render pending-stall overlays for long-running pending workflows', () => {
    vi.spyOn(Date, 'now').mockReturnValue(10_000)

    renderStepList({
      steps: [
        makeStep({
          step_id: 1,
          function_name: 'first_step',
          agent_name: 'Planner',
          started_at_epoch_ms: 0,
          completed_at_epoch_ms: 1_000,
        }),
        makeStep({
          step_id: 2,
          function_name: 'stopped_step',
          agent_name: 'Planner',
          started_at_epoch_ms: 2_000,
          completed_at_epoch_ms: 4_000,
        }),
      ],
    })

    expect(screen.getAllByTestId('step-gantt-bar')).toHaveLength(2)
    expect(screen.queryByTestId('downtime-gantt-bar')).not.toBeInTheDocument()
    expect(screen.getByText('running…')).toBeInTheDocument()
  })

  it('does not render refresh downtime overlays when newer rows exist', () => {
    renderStepList({
      workflow: makeWorkflow({
        status: 'SUCCESS',
        created_at: 0,
        updated_at: 9_000,
      }),
      steps: [
        makeStep({
          step_id: 1,
          function_name: 'first_step',
          agent_name: 'Planner',
          started_at_epoch_ms: 0,
          completed_at_epoch_ms: 1_000,
        }),
        makeStep({
          step_id: 2,
          function_name: 'crashed_step',
          agent_name: 'Planner',
          started_at_epoch_ms: 2_000,
          completed_at_epoch_ms: 4_000,
        }),
        makeStep({
          step_id: 3,
          function_name: 'resumed_step',
          agent_name: 'Planner',
          started_at_epoch_ms: 8_000,
          completed_at_epoch_ms: 9_000,
        }),
      ],
      resolvedRefreshDowntimes: [
        {
          start: 4_000,
          end: 8_000,
          source: 'refresh',
          anchorStepId: 2,
        },
      ],
    })

    expect(screen.getAllByTestId('step-gantt-bar')).toHaveLength(3)
    expect(screen.queryByTestId('downtime-gantt-bar')).not.toBeInTheDocument()
  })

  it('rebases old inherited fork history so current running steps stay visible', () => {
    vi.spyOn(Date, 'now').mockReturnValue(12_000)

    renderStepList({
      workflow: makeWorkflow({
        workflow_id: 'wf-forked',
        status: 'PENDING',
        created_at: 10_000,
        updated_at: 10_000,
        forked_from: 'wf-source',
      }),
      steps: [
        makeStep({
          step_id: 1,
          function_name: 'old_step',
          started_at_epoch_ms: 1_000,
          completed_at_epoch_ms: 2_000,
        }),
        makeStep({
          step_id: 2,
          function_name: 'current_step',
          started_at_epoch_ms: 11_000,
          completed_at_epoch_ms: null,
          display_completed_at_epoch_ms: undefined as unknown as null,
          duration_ms: null,
          display_duration_ms: undefined as unknown as null,
        }),
      ],
    })

    const bars = screen.getAllByTestId('step-gantt-bar')
    expect(bars[0]).toHaveStyle({ left: '0%', width: '33.33333333333333%' })
    expect(bars[1]).toHaveStyle({ left: '66.66666666666666%', width: '33.33333333333333%' })
    expect(screen.getByText('running…')).toBeInTheDocument()
  })
})
