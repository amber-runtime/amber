import type { Step, AgentGroup, WorkflowInfo, ModelPricing } from './types'
import { getPricing } from './pricingStore'

export type StepKind = 'llm' | 'tool' | 'sleep' | 'other'

export function humanizeStepName(functionName: string | null): string {
  if (!functionName) return 'Unknown'
  const map: Record<string, string> = {
    _model_call_step: 'Agent Turn',
    search_web: 'Web Search',
    'DBOS.sleep': 'Sleep',
  }
  if (map[functionName]) return map[functionName]
  return functionName
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function humanizeWorkflowName(name: string): string {
  if (!name) return 'Workflow'
  // Handle legacy underscore names from old single_server_poc runs
  const underscoreMap: Record<string, string> = {
    run_agent: 'Research Agent',
    run_email_campaign: 'Email Campaign',
  }
  if (underscoreMap[name]) return underscoreMap[name]
  // Handle slug format: "research-assistant" → "Research Assistant"
  return name
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export function getStepKind(step: Step): StepKind {
  if (step.event_type === 'llm_response') return 'llm'
  if (step.event_type === 'tool_call') return 'tool'
  if (step.function_name === 'DBOS.sleep') return 'sleep'
  return 'other'
}

export function sumTokens(steps: Step[]): number {
  return steps.reduce((sum, step) => {
    return sum + (step.tokens_in ?? 0) + (step.tokens_out ?? 0)
  }, 0)
}

export function sumTokensIn(steps: Step[]): number {
  return steps.reduce((sum, step) => sum + (step.tokens_in ?? 0), 0)
}

export function sumTokensOut(steps: Step[]): number {
  return steps.reduce((sum, step) => sum + (step.tokens_out ?? 0), 0)
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rem = Math.round(s % 60)
  return `${m}m ${rem}s`
}

export function formatRelativeTime(epochMs: number): string {
  const diffMs = Date.now() - epochMs
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins} min ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'yesterday'
  return `${diffDays} days ago`
}

export function formatTimestamp(epochMs: number): string {
  return new Date(epochMs).toLocaleString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

export function parseSearchWebOutput(
  raw: string,
): Array<{ title: string; url: string; summary: string }> {
  return raw
    .split('\n---\n')
    .map((block) => {
      const titleMatch = block.match(/^Title: (.+)/m)
      const urlMatch = block.match(/^URL: (.+)/m)
      const summaryMatch = block.match(/^Summary: ([\s\S]+)/m)
      return {
        title: titleMatch?.[1]?.trim() ?? '',
        url: urlMatch?.[1]?.trim() ?? '',
        summary: summaryMatch?.[1]?.trim() ?? '',
      }
    })
    .filter((r) => r.title || r.url)
}

export function stepDurationMs(step: Step): number | null {
  return step.duration_ms
}


export function groupStepsByAgent(steps: Step[]): AgentGroup[] {
  if (steps.length === 0) return []

  const groups: AgentGroup[] = []
  let currentAgentName: string | null = null
  let currentSteps: Step[] = []
  let seenAnyAgent = false

  const flush = () => {
    if (currentSteps.length === 0) return
    const startedAtMs = currentSteps[0].started_at_epoch_ms ?? null
    const endedAtMs = currentSteps[currentSteps.length - 1].completed_at_epoch_ms ?? null
    groups.push({
      agentName: currentAgentName,
      steps: currentSteps,
      startedAtMs,
      endedAtMs,
      totalDurationMs: startedAtMs != null && endedAtMs != null ? endedAtMs - startedAtMs : null,
    })
    currentSteps = []
  }

  for (const step of steps) {
    const agentName = step.agent_name ?? null

    if (agentName !== null) {
      if (!seenAnyAgent || agentName !== currentAgentName) {
        flush()
        currentAgentName = agentName
        seenAnyAgent = true
      }
      currentSteps.push(step)
    } else {
      // Infrastructure step (event_type='step', no agent_name).
      // Before any agent runs → preflight. After → attach to the current agent group.
      currentSteps.push(step)
    }
  }

  flush()
  return groups
}

const WORKFLOW_WINDOW_MIN_MS = 5000
const BAR_MIN_WIDTH_PCT = 0.5

export interface StepBarGeometry {
  leftPct: number
  widthPct: number
  inProgress: boolean
}

const TERMINAL_WORKFLOW_STATUSES: ReadonlySet<string> = new Set([
  'SUCCESS',
  'ERROR',
  'CANCELLED',
  'FAILURE',
])

function isFiniteNumber(n: unknown): n is number {
  return typeof n === 'number' && Number.isFinite(n)
}

function stepDerivedEnd(steps: Step[], fallback: number): number {
  if (steps.length === 0) return fallback
  const last = steps[steps.length - 1]
  return last.completed_at_epoch_ms ?? last.started_at_epoch_ms ?? fallback
}

export function computeWorkflowWindow(
  workflow: WorkflowInfo,
  steps: Step[],
): { start: number; end: number } {
  const start = isFiniteNumber(workflow.created_at)
    ? workflow.created_at
    : steps[0]?.started_at_epoch_ms ?? Date.now()

  const isTerminal = TERMINAL_WORKFLOW_STATUSES.has(workflow.status)
  let end: number
  if (isTerminal) {
    end = isFiniteNumber(workflow.updated_at)
      ? workflow.updated_at
      : stepDerivedEnd(steps, start)
  } else {
    end = Date.now()
  }

  return { start, end: Math.max(end, start + WORKFLOW_WINDOW_MIN_MS) }
}

export function computeStepBarGeometry(
  step: Step,
  workflowStart: number,
  workflowEnd: number,
): StepBarGeometry {
  const totalDuration = Math.max(workflowEnd - workflowStart, 1)
  const stepStart = step.started_at_epoch_ms ?? workflowStart
  const inProgress = step.completed_at_epoch_ms == null
  const stepEnd = step.completed_at_epoch_ms ?? workflowEnd
  const leftPct = ((stepStart - workflowStart) / totalDuration) * 100
  const widthPct = Math.max(((stepEnd - stepStart) / totalDuration) * 100, BAR_MIN_WIDTH_PCT)
  return { leftPct, widthPct, inProgress }
}

const RECOVERY_GAP_MIN_MS = 1000

// Largest period during which no step was active. Uses a running max-end so
// overlapping concurrent steps don't register as gaps. Returns null if no gap
// meets the minimum threshold.
export function findLargestRecoveryGap(
  steps: Step[],
): { start: number; end: number } | null {
  const intervals = steps
    .filter(
      (s) =>
        s.started_at_epoch_ms != null && s.completed_at_epoch_ms != null,
    )
    .map((s) => ({
      start: s.started_at_epoch_ms as number,
      end: s.completed_at_epoch_ms as number,
    }))
    .sort((a, b) => a.start - b.start)

  if (intervals.length < 2) return null

  let best: { start: number; end: number } | null = null
  let runningMaxEnd = intervals[0].end
  for (let i = 1; i < intervals.length; i++) {
    const gapMs = intervals[i].start - runningMaxEnd
    if (gapMs >= RECOVERY_GAP_MIN_MS) {
      if (best == null || gapMs > best.end - best.start) {
        best = { start: runningMaxEnd, end: intervals[i].start }
      }
    }
    if (intervals[i].end > runningMaxEnd) runningMaxEnd = intervals[i].end
  }
  return best
}

const DATE_SUFFIX_RE = /-\d{4}-\d{2}-\d{2}$/
const _warnedModels = new Set<string>()

function lookupPricing(model: string): ModelPricing | null {
  const table = getPricing()
  const direct = table[model]
  if (direct) return direct
  const stripped = model.replace(DATE_SUFFIX_RE, '')
  if (stripped !== model) {
    const fallback = table[stripped]
    if (fallback) return fallback
  }
  if (!_warnedModels.has(model)) {
    _warnedModels.add(model)
    console.warn(`No pricing entry for model: ${model}`)
  }
  return null
}

// LiteLLM stores prices as USD per token, so we multiply directly (no /1M).
// Cache fields are intentionally ignored for MVP.
export function estimateCost(steps: Step[]): number | null {
  let total = 0
  let priced = 0
  for (const step of steps) {
    if (!step.llm_model) continue
    if (step.tokens_in == null && step.tokens_out == null) continue
    const price = lookupPricing(step.llm_model)
    if (!price) continue
    total += (step.tokens_in ?? 0) * price.input
    total += (step.tokens_out ?? 0) * price.output
    priced++
  }
  return priced === 0 ? null : total
}

export interface CostBreakdownEntry {
  model: string
  inputTokens: number
  inputRate: number | null
  inputCost: number | null
  outputTokens: number
  outputRate: number | null
  outputCost: number | null
  subtotal: number | null
}

// Per-model token totals + cost math. Models without a pricing entry are
// included with null rate/cost fields so the UI can render "no pricing
// available" instead of silently dropping them.
export function computeCostBreakdown(steps: Step[]): CostBreakdownEntry[] {
  const totals = new Map<string, { in: number; out: number }>()
  for (const step of steps) {
    if (!step.llm_model) continue
    if (step.tokens_in == null && step.tokens_out == null) continue
    const cur = totals.get(step.llm_model) ?? { in: 0, out: 0 }
    cur.in += step.tokens_in ?? 0
    cur.out += step.tokens_out ?? 0
    totals.set(step.llm_model, cur)
  }

  const out: CostBreakdownEntry[] = []
  for (const [model, toks] of totals) {
    const price = lookupPricing(model)
    if (price == null) {
      out.push({
        model,
        inputTokens: toks.in,
        inputRate: null,
        inputCost: null,
        outputTokens: toks.out,
        outputRate: null,
        outputCost: null,
        subtotal: null,
      })
    } else {
      const inputCost = toks.in * price.input
      const outputCost = toks.out * price.output
      out.push({
        model,
        inputTokens: toks.in,
        inputRate: price.input,
        inputCost,
        outputTokens: toks.out,
        outputRate: price.output,
        outputCost,
        subtotal: inputCost + outputCost,
      })
    }
  }
  return out
}

export function formatCost(cost: number | null): string {
  if (cost == null) return '—'
  if (cost > 0 && cost < 0.01) return '<$0.01'
  return `$${cost.toFixed(2)}`
}

export function countLlmCalls(steps: Step[]): number {
  return steps.reduce((n, s) => (getStepKind(s) === 'llm' ? n + 1 : n), 0)
}

export function countToolCalls(steps: Step[]): number {
  return steps.reduce((n, s) => (getStepKind(s) === 'tool' ? n + 1 : n), 0)
}

// Case-insensitive substring match across the user-visible step fields.
// Empty query returns an empty set; the caller treats that as "no filter."
export function filterStepsBySearch(steps: Step[], query: string): Set<number> {
  const q = query.trim().toLowerCase()
  const matches = new Set<number>()
  if (q === '') return matches
  for (const step of steps) {
    if (step.step_id == null) continue
    const haystack = [
      humanizeStepName(step.function_name),
      step.function_name,
      step.tool_name,
      step.agent_name,
      step.llm_model,
    ]
      .filter((s): s is string => typeof s === 'string')
      .join(' ')
      .toLowerCase()
    if (haystack.includes(q)) matches.add(step.step_id)
  }
  return matches
}
