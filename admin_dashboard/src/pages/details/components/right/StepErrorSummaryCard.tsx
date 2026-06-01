import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Step, SelectedStepId } from '../../../../lib/types'
import { humanizeStepName } from '../../../../lib/stepHelpers'

interface Props {
  steps: Step[]
  selectedStepId: SelectedStepId
  onSelectStep: (stepId: number) => void
}

export function StepErrorSummaryCard({
  steps,
  selectedStepId,
  onSelectStep,
}: Props) {
  const [expanded, setExpanded] = useState(false)
  const erroredSteps = useMemo(
    () =>
      steps
        .filter((step) => step.status === 'ERROR' && step.step_id != null)
        .sort((a, b) => (b.step_id ?? 0) - (a.step_id ?? 0)),
    [steps],
  )

  const errorCount = erroredSteps.length
  const hasErrors = errorCount > 0
  const cardClass = hasErrors
    ? 'border-red-500/70 text-red-200 bg-red-500/5'
    : 'border-slate-800 text-slate-500 bg-slate-900'

  const handleToggle = () => {
    if (!hasErrors) return
    setExpanded((prev) => !prev)
  }

  return (
    <div className={`border rounded-lg overflow-hidden ${cardClass}`}>
      <button
        type="button"
        onClick={handleToggle}
        disabled={!hasErrors}
        aria-expanded={hasErrors ? expanded : undefined}
        className={`w-full flex items-center gap-2 px-3 py-2 text-left text-xs font-medium ${
          hasErrors ? 'cursor-pointer hover:bg-red-500/10' : 'cursor-default'
        }`}
      >
        <span className="flex-1">Step errors: {errorCount}</span>
        {hasErrors ? (
          expanded ? <ChevronDown size={14} className="shrink-0" /> : <ChevronRight size={14} className="shrink-0" />
        ) : null}
      </button>

      {expanded && hasErrors && (
        <div className="border-t border-red-500/30 divide-y divide-red-500/20">
          {erroredSteps.map((step) => {
            const isSelected = step.step_id === selectedStepId
            const name = step.event_type === 'tool_call'
              ? humanizeStepName(step.tool_name ?? step.function_name)
              : humanizeStepName(step.function_name)
            return (
              <button
                key={step.step_id}
                type="button"
                onClick={() => {
                  onSelectStep(step.step_id!)
                  setExpanded(false)
                }}
                className={`w-full px-3 py-2 text-left text-xs transition-colors ${
                  isSelected
                    ? 'bg-red-500/15 text-red-100'
                    : 'text-red-200 hover:bg-red-500/10'
                }`}
              >
                <span className="font-mono text-[11px] text-red-300/80">step #{step.step_id}</span>
                <span className="ml-2">{name}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
