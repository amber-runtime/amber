import { useEffect, useRef, useState } from 'react'
import {
  Brain,
  Search,
  Clock,
  Wrench,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Step, LLMFunctionCallItem, LLMMessageItem } from '../lib/types'
import {
  getStepKind,
  humanizeStepName,
  formatDuration,
  parseSearchWebOutput,
  isLLMOutput,
  stepDurationMs,
} from '../lib/stepHelpers'

interface Props {
  step: Step
  index: number
  isActive: boolean
}

function CopyInline({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        navigator.clipboard.writeText(text).catch(() => undefined)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      className="ml-1 inline-flex items-center p-0.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
    </button>
  )
}

function StepIcon({ functionName }: { functionName: string }) {
  const kind = getStepKind(functionName)
  const cls = 'shrink-0'
  if (kind === 'llm') return <Brain size={15} className={`${cls} text-slate-500`} />
  if (kind === 'sleep') return <Clock size={15} className={`${cls} text-gray-400`} />
  if (functionName === 'search_web') return <Search size={15} className={`${cls} text-emerald-500`} />
  return <Wrench size={15} className={`${cls} text-sky-500`} />
}

function StatusDot({ step }: { step: Step }) {
  if (step.error)
    return <XCircle size={14} className="text-red-500 shrink-0" />
  if (step.completed_at_epoch_ms == null)
    return <Loader2 size={14} className="text-amber-500 shrink-0 animate-spin" />
  return <CheckCircle2 size={14} className="text-green-500 shrink-0" />
}

function LLMStepBody({ step }: { step: Step }) {
  if (!isLLMOutput(step.output)) return null
  const { output: items, usage, response_id, model } = step.output

  return (
    <div className="space-y-3">
      {/* Metadata row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 font-mono bg-gray-50 rounded px-3 py-2">
        {model && <span className="text-gray-700">{model}</span>}
        <span>{usage.input_tokens.toLocaleString()} in</span>
        <span>{usage.output_tokens.toLocaleString()} out</span>
        <span className="text-gray-700 font-semibold">{usage.total_tokens.toLocaleString()} total</span>
        <span className="text-gray-400 ml-auto flex items-center">
          {response_id.slice(0, 28)}…
          <CopyInline text={response_id} />
        </span>
      </div>

      {/* Output items */}
      {items.map((item, i) => {
        if (item.type === 'function_call') {
          const fc = item as LLMFunctionCallItem
          let parsed: unknown = fc.arguments
          try {
            parsed = JSON.parse(fc.arguments)
          } catch {
            // leave as string
          }
          return (
            <div key={i} className="flex items-start gap-2 text-sm">
              <span className="text-gray-400 mt-0.5 shrink-0">→</span>
              <span>
                <span className="text-gray-500">Requested </span>
                <code className="font-mono text-slate-700 text-xs bg-slate-100 px-1 py-0.5 rounded">
                  {fc.name}
                </code>
                <pre className="mt-1.5 text-xs bg-gray-50 rounded p-2 overflow-x-auto text-gray-700 font-mono leading-relaxed">
                  {typeof parsed === 'object'
                    ? JSON.stringify(parsed, null, 2)
                    : String(parsed)}
                </pre>
              </span>
            </div>
          )
        }

        if (item.type === 'message') {
          const msg = item as LLMMessageItem
          const text = msg.content?.[0]?.text
          if (!text) return null
          return (
            <div key={i}>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Final Answer Generation
              </p>
              <div className="prose text-sm text-gray-800 max-w-none">
                <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
              </div>
            </div>
          )
        }

        return null
      })}
    </div>
  )
}

function SearchWebBody({ output }: { output: string }) {
  const results = parseSearchWebOutput(output)
  if (results.length === 0) {
    return <pre className="text-xs font-mono bg-gray-50 rounded p-3 overflow-x-auto">{output}</pre>
  }
  return (
    <div className="space-y-3">
      {results.map((r, i) => (
        <div key={i} className="border border-gray-100 rounded-lg px-4 py-3 space-y-1">
          <p className="text-sm font-medium text-gray-800">{r.title}</p>
          <a
            href={r.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline block truncate"
          >
            {r.url}
          </a>
          <p className="text-xs text-gray-600 leading-relaxed">{r.summary}</p>
        </div>
      ))}
    </div>
  )
}

function OtherToolBody({ step }: { step: Step }) {
  const payload = {
    output: step.output,
    error: step.error,
  }
  return (
    <pre className="text-xs font-mono bg-gray-50 rounded p-3 overflow-x-auto text-gray-700 leading-relaxed">
      {JSON.stringify(payload, null, 2)}
    </pre>
  )
}

function SleepBody({ step }: { step: Step }) {
  const dur = stepDurationMs(step)
  return (
    <p className="text-sm text-gray-400 italic">
      Slept for {dur != null ? formatDuration(dur) : '…'}
    </p>
  )
}

function ExpandedBody({ step }: { step: Step }) {
  const kind = getStepKind(step.function_name)

  if (kind === 'llm') return <LLMStepBody step={step} />

  if (kind === 'sleep') return <SleepBody step={step} />

  if (step.function_name === 'search_web' && typeof step.output === 'string') {
    return <SearchWebBody output={step.output} />
  }

  return <OtherToolBody step={step} />
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
  const kind = getStepKind(step.function_name)
  const isSleep = kind === 'sleep'
  const humanName = humanizeStepName(step.function_name)
  const hasError = !!step.error
  const inProgress = step.completed_at_epoch_ms == null

  return (
    <div
      ref={cardRef}
      className={`bg-white border rounded-lg overflow-hidden transition-shadow ${
        hasError ? 'border-red-300' : isActive ? 'border-slate-400 shadow-sm' : 'border-gray-200'
      }`}
    >
      {/* Header — always visible */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Step number */}
        <span className="w-6 h-6 rounded-full bg-gray-100 text-gray-500 text-xs font-semibold flex items-center justify-center shrink-0">
          {index + 1}
        </span>

        <StepIcon functionName={step.function_name} />

        <span
          className={`flex-1 text-sm font-medium ${
            isSleep ? 'text-gray-400' : 'text-gray-800'
          } ${isSleep ? 'text-xs' : ''}`}
        >
          {humanName}
        </span>

        <StatusDot step={step} />

        {dur != null && (
          <span className="text-xs text-gray-400 font-mono shrink-0">{formatDuration(dur)}</span>
        )}
        {inProgress && (
          <span className="text-xs text-amber-500 font-mono shrink-0">running…</span>
        )}

        <span className="text-gray-300 shrink-0">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {/* Error preview — visible when collapsed */}
      {hasError && !expanded && (
        <div className="px-4 pb-3 border-l-2 border-red-400 ml-4">
          <p className="text-xs text-red-600 font-mono leading-relaxed line-clamp-2">
            {step.error}
          </p>
        </div>
      )}

      {/* Expanded body */}
      {expanded && (
        <div
          className={`px-4 pb-4 border-t border-gray-100 pt-3 ${
            hasError ? 'border-l-2 border-l-red-400 ml-4' : ''
          }`}
        >
          {hasError && (
            <div className="mb-3">
              <p className="text-xs font-semibold text-red-600 mb-1">Error</p>
              <pre className="text-xs font-mono text-red-700 bg-red-50 rounded p-2.5 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                {step.error}
              </pre>
            </div>
          )}
          {!hasError && <ExpandedBody step={step} />}
        </div>
      )}
    </div>
  )
}
