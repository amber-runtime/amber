import {
  Brain,
  Clock,
  Search,
  Wrench,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import type { Step } from '../../../lib/types'
import {
  computeStepBarGeometry,
  formatDuration,
  getStepKind,
  humanizeStepName,
  stepCompletedAtMs,
  stepDurationMs,
} from '../../../lib/stepHelpers'

interface Props {
  step: Step
  isSelected: boolean
  onClick: (stepId: number) => void
  workflowStart: number
  workflowEnd: number
}

function StepIcon({ step }: { step: Step }) {
  const kind = getStepKind(step)
  const cls = 'shrink-0'
  if (kind === 'llm') return <Brain size={13} className={`${cls} text-slate-400`} />
  if (kind === 'sleep') return <Clock size={13} className={`${cls} text-slate-600`} />
  if (step.tool_name === 'search_web' || step.function_name === 'search_web')
    return <Search size={13} className={`${cls} text-emerald-400`} />
  return <Wrench size={13} className={`${cls} text-sky-400`} />
}

function StatusDot({ step }: { step: Step }) {
  if (step.status === 'ERROR')
    return <XCircle size={13} className="text-red-400 shrink-0" />
  if (stepCompletedAtMs(step) == null) {
    return (
      <span className="relative inline-flex h-3 w-3 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500" />
      </span>
    )
  }
  return <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
}

function barColorClass(step: Step): string {
  if (step.status === 'ERROR') return 'bg-red-500/80'
  if (stepCompletedAtMs(step) == null) return 'bg-amber-500/70'
  return 'bg-emerald-500/70'
}

function StepBar({
  step,
  workflowStart,
  workflowEnd,
}: {
  step: Step
  workflowStart: number
  workflowEnd: number
}) {
  const hasTiming = step.started_at_epoch_ms != null
  const geom = hasTiming
    ? computeStepBarGeometry(step, workflowStart, workflowEnd)
    : null
  return (
    <div className="relative h-3 rounded-sm bg-slate-800/60 overflow-hidden">
      {geom != null && (
        <span
          className={`absolute top-0 h-full min-w-[2px] rounded-sm ${barColorClass(step)}`}
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
}: Props) {
  const stepId = step.step_id
  const kind = getStepKind(step)
  const hasError = step.status === 'ERROR'
  const inProgress = stepCompletedAtMs(step) == null
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

  const tooltip = `${name}${dur != null ? ` · ${formatDuration(dur)}` : ' · in progress'}`

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
        <StatusDot step={step} />
        <StepIcon step={step} />
        <span className={`text-xs truncate ${nameClass}`}>{name}</span>
      </div>

      {/* Middle: timeline bar */}
      <StepBar
        step={step}
        workflowStart={workflowStart}
        workflowEnd={workflowEnd}
      />

      {/* Right: duration */}
      <span className="text-[11px] font-mono text-slate-500 tabular-nums text-right shrink-0">
        {kind === 'sleep' && dur != null ? formatDuration(dur) : inProgress ? 'running…' : dur != null ? formatDuration(dur) : '—'}
      </span>
    </button>
  )
}
