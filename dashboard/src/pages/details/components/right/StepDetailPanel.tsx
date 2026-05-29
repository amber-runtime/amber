import { useEffect, useState } from 'react'
import {
  Brain,
  Clock,
  GitFork,
  Loader2,
  Search,
  Wrench,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import type { Step } from '../../../../lib/types'
import {
  canForkFromStep,
  formatDuration,
  formatTimestamp,
  getStepKind,
  humanizeStepName,
  stepCompletedAtMs,
  stepDurationMs,
  stepStartedAtMs,
} from '../../../../lib/stepHelpers'
import { forkWorkflow } from '../../../../lib/api'
import { showToast } from '../../../../shared/Toast'
import { Section } from './Section'
import { JsonBlock } from './JsonBlock'
import { LLMMessagesBlock } from './LLMMessagesBlock'
import { OutputRenderer } from './OutputRenderer'
import { DefList } from './DefList'

interface Props {
  workflowId: string
  step: Step
  steps: Step[]
  onForkSuccess?: (forkedWorkflowId: string) => void
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
  if (stepCompletedAtMs(step) == null)
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

export function StepDetailPanel({ workflowId, step, steps, onForkSuccess }: Props) {
  const [now, setNow] = useState(Date.now())
  const [forkPending, setForkPending] = useState(false)
  const kind = getStepKind(step)
  const humanName = step.event_type === 'tool_call'
    ? humanizeStepName(step.tool_name ?? step.function_name)
    : humanizeStepName(step.function_name)

  const startedAt = stepStartedAtMs(step)
  const completedAt = stepCompletedAtMs(step)
  const dur = stepDurationMs(step)
  const isRunningSleep = kind === 'sleep' && completedAt == null && startedAt != null
  const displayDurationMs = isRunningSleep
    ? Math.max(now - startedAt, 0)
    : dur

  useEffect(() => {
    if (!isRunningSleep) return
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [isRunningSleep])

  const timingRows: Array<[string, string]> = [
    ['Started', startedAt != null ? formatTimestamp(startedAt) : '—'],
    ['Completed', completedAt != null ? formatTimestamp(completedAt) : 'Still running'],
    ['Duration', displayDurationMs != null ? formatDuration(displayDurationMs) : '—'],
  ]

  const hasError = step.status === 'ERROR'
  const llmHasIO = kind === 'llm' && (step.llm_input != null || step.llm_output != null)
  const llmHasTokens =
    kind === 'llm' && (step.tokens_in != null || step.tokens_out != null)
  const canFork = canForkFromStep(steps, step.step_id)

  const handleFork = async () => {
    if (!canFork || forkPending || step.step_id == null) return
    setForkPending(true)
    try {
      const result = await forkWorkflow(workflowId, step.step_id)
      onForkSuccess?.(result.forkedWorkflowId)
    } catch (err) {
      showToast(
        'Fork failed',
        err instanceof Error ? err.message : 'Unknown error',
      )
    } finally {
      setForkPending(false)
    }
  }

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
        <div className="mt-3">
          {/* Fork button */}
          <button
            type="button"
            onClick={() => void handleFork()}
            disabled={!canFork || forkPending}
            title={
              canFork
                ? 'Creates a new workflow from this step and runs it. This workflow stays unchanged.'
                : 'Fork requires a complete attempted step history through this step.'
            }
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border-2 shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${
              !canFork || forkPending
                ? 'border-slate-800 text-slate-600 bg-slate-900 cursor-not-allowed opacity-60 shadow-none'
                : 'border-slate-500 text-slate-50 bg-slate-800 shadow-black/30 hover:bg-slate-700 hover:border-slate-300'
            }`}
          >
            {forkPending ? <Loader2 size={13} className="animate-spin" /> : <GitFork size={13} />}
            Fork as New Run
          </button>
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
          <OutputRenderer value={step.step_output} />
        </Section>
      )}

      {/* Error — only when present */}
      {hasError && (
        <Section title="Error" defaultExpanded>
          {step.error_message ? (
            <OutputRenderer
              value={step.error_message}
              maxHeight="max-h-40"
              textClassName="text-red-300"
            />
          ) : (
            <p className="text-xs text-red-300">
              This step failed. The backend does not yet expose the error message —
              check the workflow status page for diagnostics.
            </p>
          )}
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
                <OutputRenderer value={step.tool_result} />
              </div>
            )}
            {step.tool_result == null && step.step_output != null && (
              <div>
                <SectionLabel>Result</SectionLabel>
                <OutputRenderer value={step.step_output} />
              </div>
            )}
            {step.tool_args == null && step.tool_result == null && step.step_output == null && (
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
              ...(step.llm_model
                ? ([['Model', step.llm_model]] as Array<[string, string]>)
                : []),
            ]}
          />
        </Section>
      )}

      {/* Sleep — durable sleep steps */}
      {kind === 'sleep' && (
        <Section title="Sleep" defaultExpanded>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-semibold text-slate-100 tabular-nums">
              {displayDurationMs != null
                ? (displayDurationMs / 1000).toFixed(displayDurationMs < 10000 ? 1 : 0)
                : '—'}
            </span>
            <span className="text-sm text-slate-400">seconds</span>
          </div>
        </Section>
      )}
    </div>
  )
}
