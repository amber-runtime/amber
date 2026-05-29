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
  computeDowntimeBarGeometry,
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
    return <span className="inline-flex h-3 w-3 shrink-0 rounded-full bg-red-500/80" />
  return <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
}

function barColorClass(step: Step, visuallyRunning: boolean): string {
  if (step.status === 'ERROR') return 'bg-red-500/80'
  if (visuallyRunning) return 'bg-amber-500/70'
  if (stepCompletedAtMs(step) == null) return 'bg-red-500/70'
  return 'bg-emerald-500/70'
}

function StepBar({
  step,
  workflowStart,
  workflowEnd,
  workflowIsActive,
  downtimeIntervals,
  nowMs,
}: {
  step: Step
  workflowStart: number
  workflowEnd: number
  workflowIsActive: boolean
  downtimeIntervals: DowntimeInterval[]
  nowMs: number
}) {
  const hasTiming = stepTimelineStartedAtMs(step) != null
  const visuallyRunning = workflowIsActive && stepCompletedAtMs(step) == null
  const geom = hasTiming
    ? computeStepBarGeometry(step, workflowStart, workflowEnd)
    : null
  const downtimeGeometries = downtimeIntervals
    .map((interval) =>
      computeDowntimeBarGeometry(interval, workflowStart, workflowEnd, nowMs),
    )
    .filter((g): g is NonNullable<typeof g> => g != null)
  return (
    <div className="relative h-3 rounded-sm bg-slate-800/60 overflow-hidden">
      {geom != null && (
        <span
          data-testid="step-gantt-bar"
          className={`absolute top-0 h-full min-w-[2px] rounded-sm ${barColorClass(step, visuallyRunning)}`}
          style={{ left: `${geom.leftPct}%`, width: `${geom.widthPct}%` }}
        />
      )}
      {downtimeGeometries.map((downtimeGeom, i) => (
        <span
          key={`${downtimeGeom.leftPct}-${downtimeGeom.widthPct}-${i}`}
          data-testid="downtime-gantt-bar"
          className="absolute top-0 h-full min-w-[2px] rounded-sm bg-red-500/85"
          style={{
            left: `${downtimeGeom.leftPct}%`,
            width: `${downtimeGeom.widthPct}%`,
          }}
        />
      ))}
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
  downtimeIntervals,
  nowMs,
}: Props) {
  const stepId = step.step_id
  const kind = getStepKind(step)
  const hasError = step.status === 'ERROR'
  const unfinished = stepCompletedAtMs(step) == null
  const visuallyRunning = workflowIsActive && unfinished
  const dur = stepDurationMs(step)

  const name = step.event_type === 'tool_call'
    ? humanizeStepName(step.tool_name ?? step.function_name)
    : humanizeStepName(step.function_name)

  const rowBg = isSelected
    ? 'bg-slate-800 border-l-amber-500'
    : 'border-l-transparent hover:bg-slate-800/50'

  const nameClass = hasError
    ? 'text-red-300'
    : kind === 'sleep'
    ? 'text-slate-500'
    : 'text-slate-200'

  const tooltip = `${name}${dur != null ? ` · ${formatDuration(dur)}` : visuallyRunning ? ' · in progress' : ' · stalled'}`

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
        downtimeIntervals={downtimeIntervals}
        nowMs={nowMs}
      />

      {/* Right: duration */}
      <span className="text-[11px] font-mono text-slate-500 tabular-nums text-right shrink-0">
        {kind === 'sleep' && dur != null
          ? formatDuration(dur)
          : visuallyRunning
          ? 'running…'
          : dur != null
          ? formatDuration(dur)
          : 'stalled'}
      </span>
    </button>
  )
}
