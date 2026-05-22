import { useEffect, useRef, useState } from 'react'
import {
  Brain,
  Search,
  Clock,
  Wrench,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react'
import type { Step } from '../lib/types'
import { getStepKind, humanizeStepName, formatDuration, stepDurationMs } from '../lib/stepHelpers'

interface Props {
  step: Step
  index: number
  isActive: boolean
}

function StepIcon({ step }: { step: Step }) {
  const kind = getStepKind(step)
  const cls = 'shrink-0'
  if (kind === 'llm') return <Brain size={15} className={`${cls} text-slate-400`} />
  if (kind === 'sleep') return <Clock size={15} className={`${cls} text-slate-600`} />
  if (step.tool_name === 'search_web' || step.function_name === 'search_web')
    return <Search size={15} className={`${cls} text-emerald-400`} />
  return <Wrench size={15} className={`${cls} text-sky-400`} />
}

function StatusDot({ step }: { step: Step }) {
  if (step.status === 'ERROR')
    return <XCircle size={14} className="text-red-400 shrink-0" />
  if (step.completed_at_epoch_ms == null)
    return <Loader2 size={14} className="text-amber-400 shrink-0 animate-spin" />
  return <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
}

function LLMStepBody({ step }: { step: Step }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 font-mono bg-slate-800 rounded px-3 py-2">
        {step.llm_model && <span className="text-slate-300">{step.llm_model}</span>}
        {step.tokens_in != null && <span>{step.tokens_in.toLocaleString()} in</span>}
        {step.tokens_out != null && <span>{step.tokens_out.toLocaleString()} out</span>}
        {step.tokens_in != null && step.tokens_out != null && (
          <span className="text-slate-200 font-semibold">
            {(step.tokens_in + step.tokens_out).toLocaleString()} total
          </span>
        )}
      </div>
      {step.llm_input != null && (
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wide font-medium mb-2">LLM Input</p>
          <pre className="bg-slate-950 border border-slate-800 rounded p-3 text-xs text-slate-300 overflow-x-auto max-h-64 overflow-y-auto">
            {JSON.stringify(step.llm_input, null, 2)}
          </pre>
        </div>
      )}
      {step.llm_output != null && (
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wide font-medium mb-2">LLM Output</p>
          <pre className="bg-slate-950 border border-slate-800 rounded p-3 text-xs text-slate-300 overflow-x-auto max-h-64 overflow-y-auto">
            {JSON.stringify(step.llm_output, null, 2)}
          </pre>
        </div>
      )}
      {step.tool_args != null && (
        <div className="flex items-start gap-2 text-sm">
          <span className="text-slate-500 mt-0.5 shrink-0">→</span>
          <span>
            <span className="text-slate-400">Requested </span>
            <code className="font-mono text-slate-300 text-xs bg-slate-800 px-1 py-0.5 rounded">
              {step.tool_name ?? 'tool'}
            </code>
            <pre className="mt-1.5 text-xs bg-slate-800 rounded p-2 overflow-x-auto text-slate-300 font-mono leading-relaxed">
              {JSON.stringify(step.tool_args, null, 2)}
            </pre>
          </span>
        </div>
      )}
    </div>
  )
}

function ToolStepBody({ step }: { step: Step }) {
  if (step.tool_args == null && step.tool_result == null) {
    return <p className="text-sm text-slate-500 italic">Tool output not available.</p>
  }
  return (
    <div className="space-y-3">
      {step.tool_args != null && (
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wide font-medium mb-1">Input</p>
          <pre className="text-xs font-mono bg-slate-800 rounded p-3 overflow-x-auto text-slate-300 leading-relaxed">
            {JSON.stringify(step.tool_args, null, 2)}
          </pre>
        </div>
      )}
      {step.tool_result != null && (
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wide font-medium mb-1">Output</p>
          <pre className="text-xs font-mono bg-slate-800 rounded p-3 overflow-x-auto text-slate-300 leading-relaxed max-h-48 overflow-y-auto">
            {step.tool_result}
          </pre>
        </div>
      )}
    </div>
  )
}

function SleepBody({ step }: { step: Step }) {
  const dur = stepDurationMs(step)
  return (
    <p className="text-sm text-slate-500 italic">
      Slept for {dur != null ? formatDuration(dur) : '…'}
    </p>
  )
}

function ExpandedBody({ step }: { step: Step }) {
  const kind = getStepKind(step)
  if (kind === 'llm') return <LLMStepBody step={step} />
  if (kind === 'sleep') return <SleepBody step={step} />
  return <ToolStepBody step={step} />
}

export function StepCard({ step, index, isActive }: Props) {
  const [expanded, setExpanded] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)
  const prevActiveRef = useRef(false)

  useEffect(() => {
    if (isActive && !prevActiveRef.current) {
      setExpanded(true)
      cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
    prevActiveRef.current = isActive
  }, [isActive])

  const dur = stepDurationMs(step)
  const kind = getStepKind(step)
  const isSleep = kind === 'sleep'
  const humanName = step.event_type === 'tool_call'
    ? humanizeStepName(step.tool_name ?? step.function_name)
    : humanizeStepName(step.function_name)
  const hasError = step.status === 'ERROR'
  const inProgress = step.completed_at_epoch_ms == null

  return (
    <div
      ref={cardRef}
      className={`bg-slate-900 border rounded-lg overflow-hidden transition-shadow ${
        hasError
          ? 'border-red-500/50'
          : isActive
          ? 'border-slate-500 shadow-sm shadow-slate-700/50'
          : 'border-slate-800'
      }`}
    >
      {/* Header — always visible */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-800 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="w-6 h-6 rounded-full bg-slate-800 text-slate-400 text-xs font-semibold flex items-center justify-center shrink-0">
          {index + 1}
        </span>

        <StepIcon step={step} />

        <span
          className={`flex-1 text-sm font-medium ${
            isSleep ? 'text-slate-500 text-xs' : 'text-slate-200'
          }`}
        >
          {humanName}
        </span>

        <StatusDot step={step} />

        {dur != null && (
          <span className="text-xs text-slate-500 font-mono shrink-0">{formatDuration(dur)}</span>
        )}
        {inProgress && (
          <span className="text-xs text-amber-400 font-mono shrink-0">running…</span>
        )}

        <span className="text-slate-600 shrink-0">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div
          className={`px-4 pb-4 border-t border-slate-800 pt-3 ${
            hasError ? 'border-l-2 border-l-red-500/50 ml-4' : ''
          }`}
        >
          <ExpandedBody step={step} />
        </div>
      )}
    </div>
  )
}
