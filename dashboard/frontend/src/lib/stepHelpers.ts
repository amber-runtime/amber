import type {
  Step,
  AgentGroup,
  WorkflowInfo,
  WorkflowSummary,
  WorkflowStatus,
  ModelPricing,
} from './types'
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

export function deriveWorkflowDisplayStatus(
  workflow: Pick<WorkflowInfo, 'status'>,
  steps: Step[],
): WorkflowStatus {
  if (workflow.status === 'PENDING' && steps.some((step) => step.status === 'ERROR')) {
    return 'ERROR'
  }
  return workflow.status
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

type WorkflowDurationInput =
  | Pick<WorkflowInfo, 'status' | 'created_at' | 'updated_at'>
  | Pick<WorkflowSummary, 'status' | 'created_at' | 'completed_at'>

function isFiniteTimestamp(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

export function workflowDurationMs(
  workflow: WorkflowDurationInput,
  nowMs = Date.now(),
): number | null {
  if (!isFiniteTimestamp(workflow.created_at)) return null

  const endMs =
    workflow.status === 'PENDING'
      ? nowMs
      : 'completed_at' in workflow
        ? workflow.completed_at
        : workflow.updated_at

  if (!isFiniteTimestamp(endMs)) return null
  return Math.max(endMs - workflow.created_at, 0)
}

export function formatWorkflowDuration(
  workflow: WorkflowDurationInput,
  nowMs = Date.now(),
): string {
  const durationMs = workflowDurationMs(workflow, nowMs)
  return durationMs == null ? '—' : formatDuration(durationMs)
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

export function shortWorkflowId(id: string): string {
  return id.length > 20 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id
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

export function stepStartedAtMs(step: Step): number | null {
  if (step.display_started_at_epoch_ms !== undefined) return step.display_started_at_epoch_ms
  return step.started_at_epoch_ms
}

export function stepCompletedAtMs(step: Step): number | null {
  if (step.display_completed_at_epoch_ms !== undefined) return step.display_completed_at_epoch_ms
  return step.completed_at_epoch_ms
}

export function stepDurationMs(step: Step): number | null {
  if (step.display_duration_ms !== undefined && step.display_duration_ms != null)
    return step.display_duration_ms

  const startedAt = stepStartedAtMs(step)
  const completedAt = stepCompletedAtMs(step)
  if (startedAt != null && completedAt != null) {
    return Math.max(completedAt - startedAt, 0)
  }
  if (startedAt != null) {
    return Math.max(Date.now() - startedAt, 0)
  }
  return step.duration_ms
}

export function stepTimelineStartedAtMs(step: Step): number | null {
  if (step.timeline_started_at_epoch_ms !== undefined) return step.timeline_started_at_epoch_ms
  return stepStartedAtMs(step)
}

export function stepTimelineCompletedAtMs(step: Step): number | null {
  if (step.timeline_completed_at_epoch_ms !== undefined) return step.timeline_completed_at_epoch_ms
  return stepCompletedAtMs(step)
}

export function buildTimelineSteps(workflow: WorkflowInfo, steps: Step[]): Step[] {
  if (workflow.forked_from == null || !Number.isFinite(workflow.created_at)) return steps

  let inheritedPrefixEnd: number | null = null
  let inheritedPrefixLength = 0
  for (const step of steps) {
    const baseStart = stepStartedAtMs(step)
    const baseEnd = stepCompletedAtMs(step)
    const marker = baseEnd ?? baseStart
    if (marker == null || marker >= workflow.created_at) break
    inheritedPrefixLength += 1
    inheritedPrefixEnd = Math.max(inheritedPrefixEnd ?? marker, marker)
  }

  if (inheritedPrefixLength === 0 || inheritedPrefixEnd == null) return steps

  const shiftMs = workflow.created_at - inheritedPrefixEnd
  if (shiftMs === 0) return steps

  return steps.map((step, index) => {
    if (index >= inheritedPrefixLength) return step
    const baseStart = stepStartedAtMs(step)
    const baseEnd = stepCompletedAtMs(step)
    return {
      ...step,
      timeline_started_at_epoch_ms: baseStart != null ? baseStart + shiftMs : null,
      timeline_completed_at_epoch_ms: baseEnd != null ? baseEnd + shiftMs : null,
    }
  })
}

export function deriveVisualActiveStepId(
  workflowStatus: WorkflowStatus,
  steps: Step[],
): number | null {
  if (workflowStatus !== 'PENDING') return null

  for (let index = steps.length - 1; index >= 0; index--) {
    const step = steps[index]
    if (step.step_id != null && stepCompletedAtMs(step) == null) return step.step_id
  }

  for (let index = steps.length - 1; index >= 0; index--) {
    const step = steps[index]
    if (step.step_id != null) return step.step_id
  }

  return null
}

export function groupStepsByAgent(steps: Step[]): AgentGroup[] {
  if (steps.length === 0) return []

  const groups: AgentGroup[] = []
  let currentAgentName: string | null = null
  let currentSteps: Step[] = []
  let seenAnyAgent = false

  const flush = () => {
    if (currentSteps.length === 0) return
    const startedAtMs = stepStartedAtMs(currentSteps[0])
    const endedAtMs = stepCompletedAtMs(currentSteps[currentSteps.length - 1])
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
const ACTIVE_WORKFLOW_STATUSES: ReadonlySet<string> = new Set(['PENDING'])

export interface StepBarGeometry {
  leftPct: number
  widthPct: number
  inProgress: boolean
}

export interface DowntimeInterval {
  start: number
  end: number | null
  source: 'error' | 'refresh' | 'recovery' | 'pending-stall'
  anchorStepId?: number | null
  anchorRowKey?: string
}

export interface DowntimeBarGeometry {
  leftPct: number
  widthPct: number
}

const TERMINAL_WORKFLOW_STATUSES: ReadonlySet<string> = new Set([
  'SUCCESS',
  'ERROR',
  'CANCELLED',
  'FAILURE',
  'MAX_RECOVERY_ATTEMPTS_EXCEEDED',
])

export function isWorkflowActivelyRunning(status: string): boolean {
  return ACTIVE_WORKFLOW_STATUSES.has(status)
}

function isFiniteNumber(n: unknown): n is number {
  return typeof n === 'number' && Number.isFinite(n)
}

function stepDerivedEnd(steps: Step[], fallback: number): number {
  if (steps.length === 0) return fallback
  const last = steps[steps.length - 1]
  return stepTimelineCompletedAtMs(last) ?? stepTimelineStartedAtMs(last) ?? fallback
}

export function computeWorkflowWindow(
  workflow: WorkflowInfo,
  steps: Step[],
  visualEndOverrideMs: number | null = null,
): { start: number; end: number } {
  const earliestStepStart = steps.reduce<number | null>((earliest, step) => {
    const startedAt = stepTimelineStartedAtMs(step)
    if (!isFiniteNumber(startedAt)) return earliest
    if (earliest == null) return startedAt
    return Math.min(earliest, startedAt)
  }, null)

  const start = isFiniteNumber(workflow.created_at)
    ? earliestStepStart != null
      ? Math.min(workflow.created_at, earliestStepStart)
      : workflow.created_at
    : earliestStepStart ?? Date.now()

  const isTerminal = TERMINAL_WORKFLOW_STATUSES.has(workflow.status)
  const hasIncompleteStep = steps.some((step) => stepCompletedAtMs(step) == null)
  const latestTimelineActivity = steps.reduce<number | null>((latest, step) => {
    const candidates = [
      stepTimelineStartedAtMs(step),
      stepTimelineCompletedAtMs(step),
      step.duration_ms != null && stepTimelineStartedAtMs(step) != null
        ? (stepTimelineStartedAtMs(step) as number) + step.duration_ms
        : null,
    ].filter((value): value is number => value != null)
    for (const timestamp of candidates) {
      if (latest == null || timestamp > latest) latest = timestamp
    }
    return latest
  }, null)
  let end: number
  if (isFiniteNumber(visualEndOverrideMs)) {
    end = visualEndOverrideMs
  } else if (isTerminal) {
    end = isFiniteNumber(workflow.updated_at)
      ? workflow.updated_at
      : stepDerivedEnd(steps, start)
  } else if (hasIncompleteStep) {
    end = Date.now()
  } else if (latestTimelineActivity != null) {
    end = latestTimelineActivity
  } else {
    end = Date.now()
  }

  return { start, end: Math.max(end, start + WORKFLOW_WINDOW_MIN_MS) }
}

export function canForkFromStep(steps: Step[], selectedStepId: number | null): boolean {
  if (selectedStepId == null || selectedStepId < 1) return false
  const attemptedStepIds = new Set(
    steps
      .map((step) => step.step_id)
      .filter((stepId): stepId is number => stepId != null),
  )
  for (let stepId = 1; stepId <= selectedStepId; stepId++) {
    if (!attemptedStepIds.has(stepId)) return false
  }
  return true
}

export function computeStepBarGeometry(
  step: Step,
  workflowStart: number,
  workflowEnd: number,
): StepBarGeometry {
  const totalDuration = Math.max(workflowEnd - workflowStart, 1)
  const stepStart = stepTimelineStartedAtMs(step) ?? workflowStart
  const inProgress = stepTimelineCompletedAtMs(step) == null
  const stepEnd = stepTimelineCompletedAtMs(step) ?? workflowEnd
  const leftPct = ((stepStart - workflowStart) / totalDuration) * 100
  const widthPct = Math.max(((stepEnd - stepStart) / totalDuration) * 100, BAR_MIN_WIDTH_PCT)
  return { leftPct, widthPct, inProgress }
}

export function computeDowntimeBarGeometry(
  interval: DowntimeInterval,
  workflowStart: number,
  workflowEnd: number,
  nowMs: number,
): DowntimeBarGeometry | null {
  const totalDuration = Math.max(workflowEnd - workflowStart, 1)
  const rawStart = Math.max(interval.start, workflowStart)
  const rawEnd = Math.min(interval.end ?? nowMs, workflowEnd)
  if (rawEnd < rawStart) return null
  if (rawEnd === rawStart && interval.end != null) return null
  const leftPct = ((rawStart - workflowStart) / totalDuration) * 100
  const widthPct = Math.max(((rawEnd - rawStart) / totalDuration) * 100, BAR_MIN_WIDTH_PCT)
  return { leftPct, widthPct }
}

const RECOVERY_GAP_MIN_MS = 1000
export const PENDING_STALL_GRACE_MS = 5000

function latestStepActivity(
  steps: Step[],
): { step: Step; timestamp: number } | null {
  let latest: { step: Step; timestamp: number } | null = null
  for (const step of steps) {
    const candidates = [
      stepStartedAtMs(step),
      stepCompletedAtMs(step),
      step.duration_ms != null && step.started_at_epoch_ms != null
        ? step.started_at_epoch_ms + step.duration_ms
        : null,
    ].filter((value): value is number => value != null)
    for (const timestamp of candidates) {
      if (latest == null || timestamp > latest.timestamp) {
        latest = { step, timestamp }
      }
    }
  }
  return latest
}

// Largest period during which no step was active. Uses a running max-end so
// overlapping concurrent steps don't register as gaps. Returns null if no gap
// meets the minimum threshold.
export function findLargestRecoveryGap(
  steps: Step[],
): { start: number; end: number } | null {
  const intervals = steps
    .filter(
      (s) =>
        stepStartedAtMs(s) != null && stepCompletedAtMs(s) != null,
    )
    .map((s) => ({
      start: stepStartedAtMs(s) as number,
      end: stepCompletedAtMs(s) as number,
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

export function recoveryDowntimeInterval(
  workflow: WorkflowInfo,
  steps: Step[],
): DowntimeInterval | null {
  if ((workflow.attempts ?? 0) <= 1) return null
  const gap = findLargestRecoveryGap(steps)
  if (gap == null) return null
  const anchorStep = steps
    .filter((step) => stepCompletedAtMs(step) === gap.start)
    .sort((a, b) => (stepStartedAtMs(b) ?? 0) - (stepStartedAtMs(a) ?? 0))[0]
  return {
    ...gap,
    source: 'recovery',
    anchorStepId: anchorStep?.step_id ?? null,
  }
}

export function errorDowntimeInterval(
  workflow: WorkflowInfo,
  steps: Step[],
): DowntimeInterval | null {
  const errorSteps = steps
    .filter((step) => step.status === 'ERROR')
    .map((step) => ({
      step,
      start:
        stepStartedAtMs(step) ??
        stepCompletedAtMs(step) ??
        (isFiniteNumber(workflow.updated_at) ? workflow.updated_at : null),
    }))
    .filter((entry): entry is { step: Step; start: number } => entry.start != null)
    .sort((a, b) => a.start - b.start)

  const firstError = errorSteps[0]
  if (firstError == null) {
    if (workflow.status !== 'ERROR') return null
    const fallbackStart = isFiniteNumber(workflow.updated_at)
      ? workflow.updated_at
      : Date.now()
    const latest = latestStepActivity(steps)
    return {
      start: fallbackStart,
      end: null,
      source: 'error',
      anchorStepId: latest?.step.step_id ?? null,
    }
  }

  const nextSuccessfulStep = steps
    .map((step) => ({
      start: stepStartedAtMs(step),
      status: step.status,
    }))
    .filter(
      (entry): entry is { start: number; status: 'SUCCESS' | 'ERROR' } =>
        entry.start != null && entry.start > firstError.start && entry.status === 'SUCCESS',
    )
    .sort((a, b) => a.start - b.start)[0]

  if (nextSuccessfulStep != null) {
    return {
      start: firstError.start,
      end: nextSuccessfulStep.start,
      source: 'error',
      anchorStepId: firstError.step.step_id,
    }
  }

  const isResolvedTerminal =
    workflow.status === 'SUCCESS' ||
    workflow.status === 'CANCELLED'
  return {
    start: firstError.start,
    end: isResolvedTerminal && isFiniteNumber(workflow.updated_at)
      ? workflow.updated_at
      : null,
    source: 'error',
    anchorStepId: firstError.step.step_id,
  }
}

export function pendingStallDowntimeInterval(
  workflow: Pick<WorkflowInfo, 'status'>,
  steps: Step[],
  nowMs: number,
  graceMs: number = PENDING_STALL_GRACE_MS,
): DowntimeInterval | null {
  if (workflow.status !== 'PENDING') return null
  if (steps.length === 0) return null
  if (steps.some((step) => stepCompletedAtMs(step) == null)) return null

  const latest = latestStepActivity(steps)
  if (latest == null) return null
  if (nowMs - latest.timestamp < graceMs) return null

  return {
    start: latest.timestamp,
    end: null,
    source: 'pending-stall',
    anchorStepId: latest.step.step_id,
  }
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
