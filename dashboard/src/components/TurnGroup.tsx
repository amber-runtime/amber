import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Turn } from '../lib/types'
import { formatDuration, humanizeStepName, isLLMOutput } from '../lib/stepHelpers'
import { StepCard } from './StepCard'

interface Props {
  turn: Turn
  activeStepId: number | null
}

// ── Turn header badges ─────────────────────────────────────────────────────────

function PreflightBadge() {
  return (
    <span className="shrink-0 px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-500 ring-1 ring-gray-200">
      Pre-flight
    </span>
  )
}

function AgentBadge({ number }: { number: number }) {
  return (
    <span className="shrink-0 px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-700 ring-1 ring-slate-200">
      Turn {number}
    </span>
  )
}

function FinalBadge() {
  return (
    <span className="shrink-0 px-2 py-0.5 rounded text-xs font-semibold bg-green-50 text-green-700 ring-1 ring-green-200">
      Final Answer
    </span>
  )
}

// ── Tool name summary (e.g. "search_web ×2") ──────────────────────────────────

function ToolSummary({ toolSteps }: { toolSteps: Turn['toolSteps'] }) {
  if (toolSteps.length === 0) return null
  const counts: Record<string, number> = {}
  for (const s of toolSteps) {
    counts[s.function_name] = (counts[s.function_name] ?? 0) + 1
  }
  const parts = Object.entries(counts).map(([name, n]) => {
    const label = humanizeStepName(name)
    return n > 1 ? `${label} ×${n}` : label
  })
  return (
    <span className="text-xs text-gray-400 truncate">
      {parts.join(', ')}
    </span>
  )
}

// ── LLM stats row ─────────────────────────────────────────────────────────────

function LLMStats({ turn }: { turn: Turn }) {
  if (!turn.llmStep || !isLLMOutput(turn.llmStep.output)) return null
  const { usage, model } = turn.llmStep.output
  return (
    <>
      {model && (
        <span className="text-xs text-gray-400 font-mono hidden sm:inline">{model}</span>
      )}
      <span className="text-xs text-gray-500 font-mono shrink-0">
        {usage.input_tokens.toLocaleString()}
        <span className="text-gray-300 mx-0.5">→</span>
        {usage.output_tokens.toLocaleString()}
        <span className="text-gray-400 ml-0.5">tok</span>
      </span>
    </>
  )
}

// ── Active-step detection ──────────────────────────────────────────────────────

function turnContainsStep(turn: Turn, stepId: number | null): boolean {
  if (stepId == null) return false
  if (turn.llmStep?.function_id === stepId) return true
  return turn.toolSteps.some((s) => s.function_id === stepId)
}

// ── Border color by kind ───────────────────────────────────────────────────────

const BORDER: Record<Turn['kind'], string> = {
  preflight: 'border-l-gray-300',
  agent: 'border-l-slate-400',
  final: 'border-l-green-500',
}

// ── Component ─────────────────────────────────────────────────────────────────

export function TurnGroup({ turn, activeStepId }: Props) {
  const defaultExpanded = turn.kind !== 'preflight'
  const [expanded, setExpanded] = useState(defaultExpanded)
  const prevContainedRef = useRef(false)

  const containsActive = turnContainsStep(turn, activeStepId)

  useEffect(() => {
    if (containsActive && !prevContainedRef.current) {
      setExpanded(true)
    }
    prevContainedRef.current = containsActive
  }, [containsActive])

  const allSteps = turn.llmStep
    ? [turn.llmStep, ...turn.toolSteps]
    : turn.toolSteps
  const hasRunning = allSteps.some((s) => s.completed_at_epoch_ms == null)
  const borderWidth = turn.kind === 'preflight' ? 'border-l-2' : 'border-l-[3px]'

  return (
    <div
      className={`${borderWidth} ${BORDER[turn.kind]} bg-white border border-gray-200 rounded-lg overflow-hidden`}
    >
      {/* Header */}
      <button
        className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-left transition-colors ${
          expanded ? 'bg-gray-50' : 'bg-white hover:bg-gray-50'
        }`}
        onClick={() => setExpanded((v) => !v)}
      >
        {turn.kind === 'preflight' && <PreflightBadge />}
        {turn.kind === 'agent' && <AgentBadge number={turn.turnNumber} />}
        {turn.kind === 'final' && <FinalBadge />}

        <div className="flex-1 flex items-center gap-3 min-w-0 overflow-hidden">
          <LLMStats turn={turn} />
          <ToolSummary toolSteps={turn.toolSteps} />
        </div>

        {/* Right-side stats */}
        <div className="flex items-center gap-2 shrink-0">
          {turn.kind === 'preflight' && (
            <span className="text-xs text-gray-400">
              {allSteps.length} step{allSteps.length !== 1 ? 's' : ''}
            </span>
          )}
          {hasRunning ? (
            <span className="text-xs text-amber-500 font-medium">running…</span>
          ) : turn.totalDurationMs != null ? (
            <span className="text-xs text-gray-400 font-mono">
              {formatDuration(turn.totalDurationMs)}
            </span>
          ) : null}
          <span className="text-gray-300">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </div>
      </button>

      {/* Body */}
      {expanded && (
        <div className="px-3 pb-3 pt-2 space-y-2">
          {/* LLM step */}
          {turn.llmStep && (
            <StepCard
              step={turn.llmStep}
              index={turn.llmStep.function_id - 1}
              isActive={turn.llmStep.function_id === activeStepId}
            />
          )}

          {/* Tool steps — indented */}
          {turn.toolSteps.map((step) => (
            <div key={step.function_id} className="ml-8">
              <StepCard
                step={step}
                index={step.function_id - 1}
                isActive={step.function_id === activeStepId}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
