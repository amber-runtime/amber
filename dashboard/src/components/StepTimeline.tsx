import { useState } from 'react'
import type { Step, WorkflowInfo } from '../lib/types'
import { groupStepsIntoTurns } from '../lib/stepHelpers'
import { GanttStrip } from './GanttStrip'
import { TurnGroup } from './TurnGroup'

interface Props {
  workflow: WorkflowInfo
  steps: Step[]
}

export function StepTimeline({ workflow, steps }: Props) {
  const [activeStepId, setActiveStepId] = useState<number | null>(null)

  const turns = groupStepsIntoTurns(steps)

  const workflowStart = workflow.created_at
  const workflowEnd =
    workflow.updated_at > workflow.created_at
      ? workflow.updated_at
      : workflow.created_at + 5000

  if (steps.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg px-5 py-8 text-center">
        <p className="text-sm text-gray-400">No steps recorded yet.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <GanttStrip
        steps={steps}
        turns={turns}
        workflowStart={workflowStart}
        workflowEnd={workflowEnd}
        activeStepId={activeStepId}
        onStepClick={(id) => setActiveStepId((prev) => (prev === id ? null : id))}
      />

      <div className="space-y-2">
        {turns.map((turn) => (
          <TurnGroup
            key={turn.kind === 'preflight' ? 'preflight' : turn.turnNumber}
            turn={turn}
            activeStepId={activeStepId}
          />
        ))}
      </div>
    </div>
  )
}
