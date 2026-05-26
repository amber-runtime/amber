import {
  Brain,
  Clock,
  Search,
  Wrench,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import type { Step } from '../../../../lib/types'
import {
  formatDuration,
  formatTimestamp,
  getStepKind,
  humanizeStepName,
} from '../../../../lib/stepHelpers'
import { Section } from './Section'
import { JsonBlock } from './JsonBlock'
import { LLMMessagesBlock } from './LLMMessagesBlock'
import { SearchWebResultsBlock } from './SearchWebResultsBlock'
import { DefList } from './DefList'

interface Props {
  step: Step
}

type StepKind = ReturnType<typeof getStepKind>

function StepIcon({ step, kind }: { step: Step; kind: StepKind }) {
  const cls = 'shrink-0'
  if (kind === 'llm') return <Brain size={15} className={`${cls} text-slate-400`} />
  if (kind === 'sleep') return <Clock size={15} className={`${cls} text-slate-600`} />
  if (step.tool_name === 'search_web' || step.function_name === 'search_web')
    return <Search size={15} className={`${cls} text-emerald-400`} />
  return <Wrench size={15} className={`${cls} text-sky-400`} />
}

function StatusBadge({ step }: { step: Step }) {
  if (step.status === 'ERROR')
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-500/15 text-red-300 ring-1 ring-red-500/30">
        <XCircle size={11} />
        Error
      </span>
    )
  if (step.completed_at_epoch_ms == null)
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30">
        Running
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30">
      <CheckCircle2 size={11} />
      Success
    </span>
  )
}

function SectionLabel({ children }: { children: string }) {
  return (
    <p className="text-[10px] text-slate-400 uppercase tracking-wider font-medium mb-1.5">
      {children}
    </p>
  )
}

export function StepDetailPanel({ step }: Props) {
  const kind = getStepKind(step)
  const humanName = step.event_type === 'tool_call'
    ? humanizeStepName(step.tool_name ?? step.function_name)
    : humanizeStepName(step.function_name)

  const startedAt = step.started_at_epoch_ms
  const completedAt = step.completed_at_epoch_ms
  const dur = step.duration_ms

  const timingRows: Array<[string, string]> = [
    ['Started', startedAt != null ? formatTimestamp(startedAt) : '—'],
    ['Completed', completedAt != null ? formatTimestamp(completedAt) : 'Still running'],
    ['Duration', dur != null ? formatDuration(dur) : '—'],
  ]

  const hasError = step.status === 'ERROR'
  const llmHasIO = kind === 'llm' && (step.llm_input != null || step.llm_output != null)
  const llmHasTokens =
    kind === 'llm' && (step.tokens_in != null || step.tokens_out != null)
  const isSearchWeb =
    step.tool_name === 'search_web' || step.function_name === 'search_web'

  return (
    <div>
      {/* Header strip */}
      <div className="px-4 py-3 border-b border-slate-800 sticky top-0 bg-slate-900 z-10">
        <div className="flex items-center gap-2 mb-1.5">
          <StepIcon step={step} kind={kind} />
          <h2 className="text-sm font-semibold text-slate-100 truncate flex-1">
            {humanName}
          </h2>
          <StatusBadge step={step} />
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono">
          {step.step_id != null && <span>step #{step.step_id}</span>}
          {step.function_name && step.function_name !== humanName && (
            <span className="truncate">{step.function_name}</span>
          )}
        </div>
      </div>

      {/* Timing — always */}
      <Section title="Timing" defaultExpanded>
        <DefList rows={timingRows} />
      </Section>

      {/* Step output — kind='other' fallback (restores old StepCard StepOutputBody).
          Surfaces DBOS operation_outputs.output when no kind-specific section fires,
          e.g., tool calls whose agent_events row got dropped at the data layer. */}
      {kind === 'other' && step.step_output != null && (
        <Section title="Step output" defaultExpanded>
          <JsonBlock value={step.step_output} />
        </Section>
      )}

      {/* Error — only when present (no error message field shipped by backend yet) */}
      {hasError && (
        <Section title="Error" defaultExpanded>
          <p className="text-xs text-red-300">
            This step failed. The backend does not yet expose the error message —
            check the workflow status page for diagnostics.
          </p>
        </Section>
      )}

      {/* LLM I/O — llm steps with payloads */}
      {llmHasIO && (
        <Section title="LLM I/O" defaultExpanded>
          {step.llm_input != null && (
            <div className="mb-3">
              <SectionLabel>Input</SectionLabel>
              <LLMMessagesBlock value={step.llm_input} />
            </div>
          )}
          {step.llm_output != null && (
            <div>
              <SectionLabel>Output</SectionLabel>
              <LLMMessagesBlock value={step.llm_output} />
            </div>
          )}
        </Section>
      )}

      {/* Tool Call — tool steps */}
      {kind === 'tool' && (
        <Section title="Tool Call" defaultExpanded>
          <div className="space-y-3">
            <DefList
              rows={[['Tool', step.tool_name ?? step.function_name ?? '—']]}
            />
            {step.tool_args != null && (
              <div>
                <SectionLabel>Arguments</SectionLabel>
                <JsonBlock value={step.tool_args} />
              </div>
            )}
            {step.tool_result != null && (
              <div>
                <SectionLabel>Result</SectionLabel>
                {isSearchWeb ? (
                  <SearchWebResultsBlock raw={step.tool_result} />
                ) : (
                  <pre className="bg-slate-950 border border-slate-800 rounded p-3 text-xs text-slate-300 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                    {step.tool_result}
                  </pre>
                )}
              </div>
            )}
            {step.tool_args == null && step.tool_result == null && (
              <p className="text-sm text-slate-500 italic">Tool output not available.</p>
            )}
          </div>
        </Section>
      )}

      {/* Tokens — auxiliary, collapsed by default */}
      {llmHasTokens && (
        <Section title="Tokens" defaultExpanded={false}>
          <DefList
            rows={[
              ['Tokens in', (step.tokens_in ?? 0).toLocaleString()],
              ['Tokens out', (step.tokens_out ?? 0).toLocaleString()],
              ['Total', ((step.tokens_in ?? 0) + (step.tokens_out ?? 0)).toLocaleString()],
              ['Model', step.llm_model ?? '—'],
            ]}
          />
        </Section>
      )}

      {/* Sleep — durable sleep steps */}
      {kind === 'sleep' && (
        <Section title="Sleep" defaultExpanded>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-semibold text-slate-100 tabular-nums">
              {dur != null ? (dur / 1000).toFixed(dur < 10000 ? 1 : 0) : '—'}
            </span>
            <span className="text-sm text-slate-400">seconds</span>
          </div>
        </Section>
      )}
    </div>
  )
}
