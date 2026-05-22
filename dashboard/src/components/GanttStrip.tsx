import type { StepWithTiming, Turn } from '../lib/types'
import { getStepKind, humanizeStepName, formatDuration, stepDurationMs } from '../lib/stepHelpers'

interface Props {
  steps: StepWithTiming[]
  turns: Turn[]
  workflowStart: number
  workflowEnd: number
  activeStepId: number | null
  onStepClick: (id: number) => void
}

const KIND_COLOR: Record<ReturnType<typeof getStepKind>, string> = {
  llm: 'bg-slate-500 hover:bg-slate-400',
  tool: 'bg-emerald-500 hover:bg-emerald-400',
  sleep: 'bg-slate-700 hover:bg-slate-600',
  other: 'bg-sky-500 hover:bg-sky-400',
}

const KIND_ACTIVE: Record<ReturnType<typeof getStepKind>, string> = {
  llm: 'bg-slate-400',
  tool: 'bg-emerald-400',
  sleep: 'bg-slate-600',
  other: 'bg-sky-400',
}

const TURN_BAND: Record<Turn['kind'], (even: boolean) => string> = {
  preflight: () => 'bg-slate-800/30',
  agent: (even) => (even ? 'bg-transparent' : 'bg-slate-800/20'),
  final: () => 'bg-emerald-900/20',
}

const TICK_COUNT = 5
const ROW_HEIGHT = 30
const ROW_GAP = 2

export function GanttStrip({
  steps,
  turns,
  workflowStart,
  workflowEnd,
  activeStepId,
  onStepClick,
}: Props) {
  const totalDuration = Math.max(workflowEnd - workflowStart, 1)

  const ticks = Array.from({ length: TICK_COUNT + 1 }, (_, i) =>
    Math.round((totalDuration * i) / TICK_COUNT),
  )

  const chartHeight = Math.max(steps.length, 1) * (ROW_HEIGHT + ROW_GAP) - ROW_GAP

  let agentIndex = 0

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 border-b border-slate-800">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Execution Timeline
        </h3>
      </div>

      <div className="px-4 pt-3 pb-4 bg-slate-950">
        {/* Tick labels */}
        <div className="relative h-4 mb-1">
          {ticks.map((ms) => {
            const pct = (ms / totalDuration) * 100
            return (
              <span
                key={ms}
                className="absolute text-[10px] text-slate-500 -translate-x-1/2"
                style={{ left: `${pct}%` }}
              >
                {ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`}
              </span>
            )
          })}
        </div>

        {/* Chart area — one row per step, staircase layout */}
        <div className="relative" style={{ height: `${chartHeight}px` }}>
          {/* Turn background bands */}
          {turns.map((turn) => {
            const bandStart = turn.startedAtMs
            const bandEnd = turn.endedAtMs ?? workflowEnd
            const leftPct = Math.max(
              0,
              ((bandStart - workflowStart) / totalDuration) * 100,
            )
            const widthPct = Math.min(
              100 - leftPct,
              ((bandEnd - bandStart) / totalDuration) * 100,
            )

            let bandClass: string
            if (turn.kind === 'preflight') {
              bandClass = TURN_BAND.preflight(false)
            } else {
              bandClass = TURN_BAND[turn.kind](agentIndex % 2 === 0)
              agentIndex++
            }

            return (
              <div
                key={turn.kind === 'preflight' ? 'preflight' : turn.turnNumber}
                className={`absolute top-0 bottom-0 ${bandClass}`}
                style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
              />
            )
          })}

          {/* Turn boundary lines */}
          {turns.slice(1).map((turn) => {
            const pct = ((turn.startedAtMs - workflowStart) / totalDuration) * 100
            return (
              <div
                key={`boundary-${turn.kind === 'preflight' ? 0 : turn.turnNumber}`}
                className="absolute top-0 bottom-0 w-px bg-slate-700 z-[1]"
                style={{ left: `${pct}%` }}
              />
            )
          })}

          {/* Vertical grid lines */}
          {ticks.map((ms) => {
            const pct = (ms / totalDuration) * 100
            return (
              <div
                key={ms}
                className="absolute top-0 bottom-0 w-px bg-slate-800 z-[1]"
                style={{ left: `${pct}%` }}
              />
            )
          })}

          {/* Step bars */}
          {steps.map((step, index) => {
            const kind = getStepKind(step.function_name)
            const isActive = step.step_id === activeStepId
            const hasError = !!step.error

            const topPx = index * (ROW_HEIGHT + ROW_GAP)
            const stepStart = step.started_at_epoch_ms ?? workflowStart
            const leftPct = ((stepStart - workflowStart) / totalDuration) * 100

            const durMs =
              step.completed_at_epoch_ms != null
                ? step.completed_at_epoch_ms - stepStart
                : workflowEnd - stepStart

            const widthPct = Math.max((durMs / totalDuration) * 100, 0.5)

            const colorClass = hasError
              ? 'bg-red-500 hover:bg-red-400'
              : isActive
              ? KIND_ACTIVE[kind]
              : KIND_COLOR[kind]

            const label = humanizeStepName(step.function_name)
            const dur = stepDurationMs(step)
            const tooltip = `${label}${dur != null ? ` · ${formatDuration(dur)}` : ' · in progress'}`

            return (
              <div
                key={step.step_id ?? index}
                className="absolute z-[2] group cursor-pointer"
                style={{ top: `${topPx}px`, height: `${ROW_HEIGHT}px`, left: `${leftPct}%`, width: `${widthPct}%` }}
                onClick={() => step.step_id != null && onStepClick(step.step_id)}
                title={tooltip}
              >
                <div
                  className={`h-full w-full rounded transition-colors ${colorClass} ${
                    step.completed_at_epoch_ms == null ? 'opacity-60 animate-pulse' : ''
                  } ${isActive ? 'ring-2 ring-offset-1 ring-offset-slate-950 ring-slate-400' : ''}`}
                />
                {/* Tooltip */}
                <div className="hidden group-hover:block absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-1.5 pointer-events-none">
                  <div className="bg-slate-700 text-slate-50 text-xs rounded px-2 py-1 whitespace-nowrap shadow-lg">
                    {tooltip}
                  </div>
                  <div className="w-2 h-2 bg-slate-700 rotate-45 mx-auto -mt-1" />
                </div>
              </div>
            )
          })}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mt-3 pt-2 border-t border-slate-800">
          {(['llm', 'tool', 'sleep'] as const).map((kind) => (
            <span key={kind} className="flex items-center gap-1.5 text-xs text-slate-500">
              <span className={`w-3 h-3 rounded ${KIND_COLOR[kind].split(' ')[0]}`} />
              {kind === 'llm' ? 'LLM call' : kind === 'tool' ? 'Tool call' : 'Sleep'}
            </span>
          ))}
          <span className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className="w-3 h-3 rounded bg-red-500" />
            Error
          </span>
        </div>
      </div>
    </div>
  )
}
