import {
  Brain,
  Clock,
  Wrench,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import type { Step } from '../../../lib/types'
import type { DowntimeInterval } from '../../../lib/stepHelpers'
import {
  computeStepBarGeometry,
  formatDuration,
  getStepKind,
  humanizeStepName,
  stepCompletedAtMs,
  stepDurationMs,
  stepTimelineStartedAtMs,
} from '../../../lib/stepHelpers'

interface Props {
  step: Step
  isSelected: boolean
  onClick: (stepId: number) => void
  workflowStart: number
  workflowEnd: number
  workflowIsActive: boolean
  visualActiveStepId: number | null
  downtimeIntervals: DowntimeInterval[]
  nowMs: number
}

function StepIcon({ step }: { step: Step }) {
  const kind = getStepKind(step)
  const cls = 'shrink-0'
  if (kind === 'llm') return <Brain size={13} className={`${cls} text-slate-400`} />
  if (kind === 'sleep') return <Clock size={13} className={`${cls} text-slate-600`} />
  return <Wrench size={13} className={`${cls} text-sky-400`} />
}

function StatusDot({
  step,
  visuallyRunning,
}: {
  step: Step
  visuallyRunning: boolean
}) {
  if (step.status === 'ERROR')
    return <XCircle size={13} className="text-red-400 shrink-0" />
  if (visuallyRunning) {
    return (
      <span className="relative inline-flex h-3 w-3 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500" />
      </span>
    )
  }
  if (stepCompletedAtMs(step) == null)
    return <span className="inline-flex h-3 w-3 shrink-0 rounded-full bg-amber-500/80" />
  return <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
}

function barColorClass(step: Step, visuallyRunning: boolean): string {
  if (step.status === 'ERROR') return 'bg-red-500/80'
  if (visuallyRunning) return 'bg-amber-500/70'
  if (stepCompletedAtMs(step) == null) return 'bg-amber-500/70'
  return 'bg-emerald-500/70'
}

function StepBar({
  step,
  workflowStart,
  workflowEnd,
  workflowIsActive,
  visualActiveStepId,
  downtimeIntervals,
  nowMs,
}: {
  step: Step
  workflowStart: number
  workflowEnd: number
  workflowIsActive: boolean
  visualActiveStepId: number | null
  downtimeIntervals: DowntimeInterval[]
  nowMs: number
}) {
  const hasTiming = stepTimelineStartedAtMs(step) != null
  const hasError = step.status === 'ERROR'
  const visuallyRunning = workflowIsActive && step.step_id === visualActiveStepId
  const geom = hasTiming
    ? computeStepBarGeometry(step, workflowStart, workflowEnd)
    : null
  return (
    <div
      data-testid="step-gantt-track"
      className={`relative h-3 rounded-sm overflow-hidden bg-slate-800/60 ${
        hasError ? 'shadow-[inset_0_0_0_1.5px_rgba(239,68,68,0.85)]' : ''
      }`}
    >
      {geom != null && (
        <span
          data-testid="step-gantt-bar"
          className={`absolute top-0 h-full min-w-[2px] rounded-sm ${barColorClass(step, visuallyRunning)}`}
          style={{ left: `${geom.leftPct}%`, width: `${geom.widthPct}%` }}
        />
      )}
    </div>
  )
}

export function StepRow({
  step,
  isSelected,
  onClick,
  workflowStart,
  workflowEnd,
  workflowIsActive,
  visualActiveStepId,
  downtimeIntervals,
  nowMs,
}: Props) {
  const stepId = step.step_id
  const kind = getStepKind(step)
  const hasError = step.status === 'ERROR'
  const isIncomplete = stepCompletedAtMs(step) == null
  const visuallyRunning = workflowIsActive && stepId === visualActiveStepId
  const dur = stepDurationMs(step)

  const name = step.event_type === 'tool_call'
    ? humanizeStepName(step.tool_name ?? step.function_name)
    : humanizeStepName(step.function_name)

  const rowBg = isSelected
    ? 'bg-slate-800 border-l-amber-500'
    : hasError
    ? 'border-l-red-500/80 hover:bg-slate-800/50'
    : 'border-l-transparent hover:bg-slate-800/50'

  const nameClass = hasError
    ? 'text-red-300'
    : kind === 'sleep'
    ? 'text-slate-500'
    : 'text-slate-200'

  const tooltip = `${name}${dur != null ? ` · ${formatDuration(dur)}` : isIncomplete ? ' · in progress' : ' · —'}`

  return (
    <button
      type="button"
      onClick={() => stepId != null && onClick(stepId)}
      disabled={stepId == null}
      title={tooltip}
      className={`group w-full grid grid-cols-[minmax(180px,1fr)_minmax(0,3fr)_4rem] items-center gap-3 h-8 px-3 text-left border-l-2 transition-colors ${rowBg}`}
    >
      {/* Left: status, kind icon, name */}
      <div className="flex items-center gap-2 min-w-0">
        <StatusDot step={step} visuallyRunning={visuallyRunning} />
        <StepIcon step={step} />
        <span className={`text-xs truncate ${nameClass}`}>{name}</span>
      </div>

      {/* Middle: timeline bar */}
      <StepBar
        step={step}
        workflowStart={workflowStart}
        workflowEnd={workflowEnd}
        workflowIsActive={workflowIsActive}
        visualActiveStepId={visualActiveStepId}
        downtimeIntervals={downtimeIntervals}
        nowMs={nowMs}
      />

      {/* Right: duration */}
      <span className="text-[11px] font-mono text-slate-500 tabular-nums text-right shrink-0">
        {kind === 'sleep' && dur != null
          ? formatDuration(dur)
          : isIncomplete
          ? 'running…'
          : dur != null
          ? formatDuration(dur)
          : '—'}
      </span>
    </button>
  )
}
