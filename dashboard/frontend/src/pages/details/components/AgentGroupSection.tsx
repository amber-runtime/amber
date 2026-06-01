import { useEffect, useRef } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { AgentGroup } from '../../../lib/types'
import type { DowntimeInterval } from '../../../lib/stepHelpers'
import { formatDuration } from '../../../lib/stepHelpers'
import { StepRow } from './StepRow'

interface Props {
  group: AgentGroup
  selectedStepId: number | null
  onStepClick: (stepId: number) => void
  isExpanded: boolean
  onExpandChange: (expanded: boolean) => void
  workflowStart: number
  workflowEnd: number
  workflowIsActive: boolean
  visualActiveStepId: number | null
  downtimeIntervals: DowntimeInterval[]
  groupIndex: number
  nowMs: number
}

function stepRowKey(stepId: number | null, groupIndex: number, stepIndex: number): string {
  return stepId != null ? `step-${stepId}` : `fallback-${groupIndex}-${stepIndex}`
}

function intervalBelongsToRow(
  interval: DowntimeInterval,
  stepId: number | null,
  rowKey: string,
): boolean {
  if (interval.anchorStepId != null) return interval.anchorStepId === stepId
  if (interval.anchorRowKey != null) return interval.anchorRowKey === rowKey
  return false
}

function PreflightBadge() {
  return (
    <span className="shrink-0 px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-400 ring-1 ring-slate-700">
      Pre-flight
    </span>
  )
}

function AgentBadge({ name }: { name: string }) {
  return (
    <span className="shrink-0 px-2 py-0.5 rounded text-xs font-semibold bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30">
      {name}
    </span>
  )
}

function groupContainsStep(group: AgentGroup, stepId: number | null): boolean {
  if (stepId == null) return false
  return group.steps.some((s) => s.step_id === stepId)
}

export function AgentGroupSection({
  group,
  selectedStepId,
  onStepClick,
  isExpanded,
  onExpandChange,
  workflowStart,
  workflowEnd,
  workflowIsActive,
  visualActiveStepId,
  downtimeIntervals,
  groupIndex,
  nowMs,
}: Props) {
  const prevContainedRef = useRef(false)

  const containsSelected = groupContainsStep(group, selectedStepId)

  useEffect(() => {
    if (containsSelected && !prevContainedRef.current) onExpandChange(true)
    prevContainedRef.current = containsSelected
  }, [containsSelected, onExpandChange])

  const isAgent = group.agentName !== null
  const borderClass = isAgent
    ? 'border-l-[3px] border-l-sky-600/50'
    : 'border-l-2 border-l-slate-600'

  return (
    <div className={`${borderClass} bg-slate-900 border border-slate-800 rounded-lg overflow-hidden`}>
      {/* Header */}
      <button
        type="button"
        className={`w-full flex items-center gap-2.5 px-4 py-2 text-left transition-colors ${
          isExpanded ? 'bg-slate-800/50' : 'bg-slate-900 hover:bg-slate-800/50'
        }`}
        onClick={() => onExpandChange(!isExpanded)}
      >
        {isAgent ? <AgentBadge name={group.agentName!} /> : <PreflightBadge />}

        <div className="flex-1" />

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-slate-500">
            {group.steps.length} step{group.steps.length !== 1 ? 's' : ''}
          </span>
          {group.totalDurationMs != null ? (
            <span className="text-xs text-slate-500 font-mono">
              {formatDuration(group.totalDurationMs)}
            </span>
          ) : null}
          <span className="text-slate-600">
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </div>
      </button>

      {/* Body */}
      {isExpanded && (
        <div className="divide-y divide-slate-800/60 border-t border-slate-800">
          {group.steps.map((step, i) => {
            const rowKey = stepRowKey(step.step_id, groupIndex, i)
            const rowDowntimeIntervals = downtimeIntervals.filter((interval) =>
              intervalBelongsToRow(interval, step.step_id, rowKey),
            )
            return (
              <StepRow
                key={step.step_id ?? i}
                step={step}
                isSelected={step.step_id === selectedStepId}
                onClick={onStepClick}
                workflowStart={workflowStart}
                workflowEnd={workflowEnd}
                workflowIsActive={workflowIsActive}
                visualActiveStepId={visualActiveStepId}
                downtimeIntervals={rowDowntimeIntervals}
                nowMs={nowMs}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
