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
      {step.llm_input != null && <LLMMessages value={step.llm_input} label="LLM Input" />}
      {step.llm_output != null && <LLMMessages value={step.llm_output} label="LLM Output" />}
      {step.tool_args != null && (
        <div className="flex items-start gap-2 text-sm">
          <span className="text-slate-500 mt-0.5 shrink-0">→</span>
          <span>
            <span className="text-slate-400">Requested </span>
            <code className="font-mono text-slate-300 text-xs bg-slate-800 px-1 py-0.5 rounded">
              {step.tool_name ?? 'tool'}
            </code>
            <pre className="mt-1.5 text-xs bg-slate-800 rounded p-2 overflow-x-auto text-slate-300 font-mono leading-relaxed">
              {prettyOutput(step.tool_args)}
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
            {prettyOutput(step.tool_args)}
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

// Extract readable text from an LLM content field.
// Content can be a plain string or an array of blocks like { type, text }.
function extractContentText(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const parts = content
      .map((b) => (b && typeof b === 'object' && 'text' in b ? String((b as Record<string, unknown>).text) : null))
      .filter(Boolean)
    return parts.length > 0 ? parts.join('\n') : null
  }
  return null
}

// Render an array of LLM messages as { role, text } pairs when possible.
// Returns null if the value doesn't look like a message array.
function parseLLMMessages(value: unknown): { role: string; text: string }[] | null {
  if (!Array.isArray(value)) return null
  const messages = value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const { role, content } = item as Record<string, unknown>
    if (typeof role !== 'string') return []
    const text = extractContentText(content)
    return text != null ? [{ role, text }] : []
  })
  return messages.length > 0 ? messages : null
}

function LLMMessages({ value, label }: { value: unknown; label: string }) {
  const messages = parseLLMMessages(value)
  if (!messages) {
    return (
      <div>
        <p className="text-slate-400 text-xs uppercase tracking-wide font-medium mb-2">{label}</p>
        <pre className="bg-slate-950 border border-slate-800 rounded p-3 text-xs text-slate-300 overflow-x-auto max-h-64 overflow-y-auto">
          {prettyOutput(value)}
        </pre>
      </div>
    )
  }
  return (
    <div>
      <p className="text-slate-400 text-xs uppercase tracking-wide font-medium mb-2">{label}</p>
      <div className="space-y-2">
        {messages.map(({ role, text }, i) => (
          <div key={i} className="bg-slate-950 border border-slate-800 rounded p-3 text-xs">
            <span className="text-slate-500 font-mono uppercase text-[10px] tracking-wider">{role}</span>
            <pre className="mt-1.5 text-slate-300 whitespace-pre-wrap leading-relaxed">{text}</pre>
          </div>
        ))}
      </div>
    </div>
  )
}

function deepParse(value: unknown): unknown {
  if (typeof value === 'string') {
    try { return deepParse(JSON.parse(value)) } catch { return value }
  }
  if (Array.isArray(value)) return value.map(deepParse)
  if (value !== null && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, deepParse(v)])
    )
  return value
}

function prettyOutput(value: unknown): string {
  return JSON.stringify(deepParse(value), null, 2)
}

function StepOutputBody({ step }: { step: Step }) {
  if (step.step_output == null) {
    return <p className="text-sm text-slate-500 italic">No output recorded.</p>
  }
  return (
    <div>
      <p className="text-slate-400 text-xs uppercase tracking-wide font-medium mb-1">Output</p>
      <pre className="text-xs font-mono bg-slate-800 rounded p-3 overflow-x-auto text-slate-300 leading-relaxed max-h-48 overflow-y-auto">
        {prettyOutput(step.step_output)}
      </pre>
    </div>
  )
}

function ExpandedBody({ step }: { step: Step }) {
  const kind = getStepKind(step)
  if (kind === 'llm') return <LLMStepBody step={step} />
  if (kind === 'sleep') return <SleepBody step={step} />
  if (kind === 'other') return <StepOutputBody step={step} />
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
