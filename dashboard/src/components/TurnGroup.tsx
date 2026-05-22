import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { AgentGroup, Step } from '../lib/types'
import { formatDuration, humanizeStepName } from '../lib/stepHelpers'
import { StepCard } from './StepCard'

interface Props {
  group: AgentGroup
  activeStepId: number | null
}

// Split an agent group's steps into iterations.
// Each iteration starts at an llm_response step. Tool/infra steps before
// the first llm_response are grouped into iteration 0.
function buildIterations(steps: Step[]): Step[][] {
  const iterations: Step[][] = []
  let current: Step[] = []

  for (const step of steps) {
    if (step.event_type === 'llm_response' && current.length > 0) {
      iterations.push(current)
      current = []
    }
    current.push(step)
  }
  if (current.length > 0) iterations.push(current)
  return iterations
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

function TokenSummary({ group }: { group: AgentGroup }) {
  const totalIn = group.steps.reduce((s, step) => s + (step.tokens_in ?? 0), 0)
  const totalOut = group.steps.reduce((s, step) => s + (step.tokens_out ?? 0), 0)
  if (totalIn === 0 && totalOut === 0) return null
  return (
    <span className="text-xs text-slate-400 font-mono shrink-0">
      {totalIn.toLocaleString()}
      <span className="text-slate-700 mx-0.5">→</span>
      {totalOut.toLocaleString()}
      <span className="text-slate-500 ml-0.5">tok</span>
    </span>
  )
}

function ToolSummary({ group }: { group: AgentGroup }) {
  const toolSteps = group.steps.filter((s) => s.event_type === 'tool_call')
  if (toolSteps.length === 0) return null
  const counts: Record<string, number> = {}
  for (const s of toolSteps) {
    const name = s.tool_name ?? s.function_name ?? 'unknown'
    counts[name] = (counts[name] ?? 0) + 1
  }
  const parts = Object.entries(counts).map(([name, n]) => {
    const label = humanizeStepName(name)
    return n > 1 ? `${label} ×${n}` : label
  })
  return (
    <span className="text-xs text-slate-500 truncate">{parts.join(', ')}</span>
  )
}

function groupContainsStep(group: AgentGroup, stepId: number | null): boolean {
  if (stepId == null) return false
  return group.steps.some((s) => s.step_id === stepId)
}

export function TurnGroup({ group, activeStepId }: Props) {
  const isAgent = group.agentName !== null
  const [expanded, setExpanded] = useState(isAgent)
  const prevContainedRef = useRef(false)

  const containsActive = groupContainsStep(group, activeStepId)

  useEffect(() => {
    if (containsActive && !prevContainedRef.current) setExpanded(true)
    prevContainedRef.current = containsActive
  }, [containsActive])

  const hasRunning = group.steps.some((s) => s.completed_at_epoch_ms == null)
  const borderClass = isAgent
    ? 'border-l-[3px] border-l-sky-600/50'
    : 'border-l-2 border-l-slate-600'

  const iterations = isAgent ? buildIterations(group.steps) : []
  const multipleIterations = iterations.length > 1

  return (
    <div className={`${borderClass} bg-slate-900 border border-slate-800 rounded-lg overflow-hidden`}>
      {/* Header */}
      <button
        className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-left transition-colors ${
          expanded ? 'bg-slate-800/50' : 'bg-slate-900 hover:bg-slate-800/50'
        }`}
        onClick={() => setExpanded((v) => !v)}
      >
        {isAgent ? <AgentBadge name={group.agentName!} /> : <PreflightBadge />}

        <div className="flex-1 flex items-center gap-3 min-w-0 overflow-hidden">
          <TokenSummary group={group} />
          <ToolSummary group={group} />
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {!isAgent && (
            <span className="text-xs text-slate-500">
              {group.steps.length} step{group.steps.length !== 1 ? 's' : ''}
            </span>
          )}
          {multipleIterations && (
            <span className="text-xs text-slate-600">
              {iterations.length} iterations
            </span>
          )}
          {hasRunning ? (
            <span className="text-xs text-amber-400 font-medium">running…</span>
          ) : group.totalDurationMs != null ? (
            <span className="text-xs text-slate-500 font-mono">
              {formatDuration(group.totalDurationMs)}
            </span>
          ) : null}
          <span className="text-slate-600">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </div>
      </button>

      {/* Body */}
      {expanded && (
        <div className="px-3 pb-3 pt-2">
          {isAgent ? (
            <div className="space-y-0">
              {iterations.map((iterSteps, iterIdx) => (
                <div
                  key={iterIdx}
                  className={iterIdx > 0 ? 'border-t border-slate-800 mt-3 pt-3' : ''}
                >
                  {multipleIterations && (
                    <p className="text-[10px] text-slate-600 uppercase tracking-wider font-medium mb-2">
                      Iteration {iterIdx + 1}
                    </p>
                  )}
                  <div className="space-y-2">
                    {iterSteps.map((step, i) => (
                      <div
                        key={step.step_id ?? i}
                        className={step.event_type === 'tool_call' ? 'ml-8' : ''}
                      >
                        <StepCard
                          step={step}
                          index={i}
                          isActive={step.step_id === activeStepId}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {group.steps.map((step, i) => (
                <StepCard
                  key={step.step_id ?? i}
                  step={step}
                  index={i}
                  isActive={step.step_id === activeStepId}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
