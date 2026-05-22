import { useState } from 'react'
import type { Step, WorkflowInfo } from '../lib/types'
import { groupStepsByAgent } from '../lib/stepHelpers'
import { GanttStrip } from './GanttStrip'
import { TurnGroup } from './TurnGroup'

interface Props {
  workflow: WorkflowInfo
  steps: Step[]
}

export function StepTimeline({ workflow, steps }: Props) {
  const [activeStepId, setActiveStepId] = useState<number | null>(null)

  const groups = groupStepsByAgent(steps)

  const workflowStart = workflow.created_at
  const lastStepEnd = steps.length > 0
    ? (steps[steps.length - 1].completed_at_epoch_ms ?? steps[steps.length - 1].started_at_epoch_ms)
    : workflowStart
  const workflowEnd = Math.max(lastStepEnd ?? workflowStart, workflowStart + 5000)

  if (steps.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-lg px-5 py-8 text-center">
        <p className="text-sm text-slate-500">No steps recorded yet.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <GanttStrip
        steps={steps}
        groups={groups}
        workflowStart={workflowStart}
        workflowEnd={workflowEnd}
        activeStepId={activeStepId}
        onStepClick={(id) => setActiveStepId((prev) => (prev === id ? null : id))}
      />

      <div className="space-y-2">
        {groups.map((group, i) => (
          <TurnGroup
            key={`${group.agentName ?? 'preflight'}-${i}`}
            group={group}
            activeStepId={activeStepId}
          />
        ))}
      </div>
    </div>
  )
}
