import type { Step, StepWithTiming, Turn } from './types'

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

export function getStepKind(functionName: string | null): StepKind {
  if (!functionName) return 'other'
  if (functionName === '_model_call_step') return 'llm'
  if (functionName === 'DBOS.sleep') return 'sleep'
  return 'tool'
}

export function sumTokens(steps: Step[]): number {
  return steps.reduce((sum, step) => {
    return sum + (step.tokens_in ?? 0) + (step.tokens_out ?? 0)
  }, 0)
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

// Derives synthetic per-step timestamps from cumulative duration_ms, anchored at
// the workflow's created_at. Assumes steps execute consecutively with no gap between
// them — inter-step orchestration time is not captured by the backend and will be
// absent from the Gantt. DBOS.sleep steps work correctly since sleep duration IS
// recorded in duration_ms. PENDING (in-flight) steps get started_at but no completed_at.
export function deriveStepTimings(
  workflowCreatedAt: number,
  steps: Step[],
): StepWithTiming[] {
  let cumulativeMs = 0
  return steps.map((step) => {
    const startedAtEpochMs = workflowCreatedAt + cumulativeMs
    const durMs = step.duration_ms
    const completedAtEpochMs = durMs != null ? startedAtEpochMs + durMs : null
    cumulativeMs += durMs ?? 0
    return { ...step, started_at_epoch_ms: startedAtEpochMs, completed_at_epoch_ms: completedAtEpochMs }
  })
}

export function groupStepsIntoTurns(steps: StepWithTiming[]): Turn[] {
  const turns: Turn[] = []
  let i = 0
  let agentTurnCount = 0

  // Collect preflight steps (before the first _model_call_step)
  const preflightSteps: StepWithTiming[] = []
  while (i < steps.length && steps[i].function_name !== '_model_call_step') {
    preflightSteps.push(steps[i])
    i++
  }
  if (preflightSteps.length > 0) {
    const start = preflightSteps[0].started_at_epoch_ms
    const lastEnd = preflightSteps[preflightSteps.length - 1].completed_at_epoch_ms
    turns.push({
      turnNumber: 0,
      kind: 'preflight',
      llmStep: null,
      toolSteps: preflightSteps,
      startedAtMs: start,
      endedAtMs: lastEnd,
      totalDurationMs: lastEnd != null ? lastEnd - start : null,
    })
  }

  while (i < steps.length) {
    if (steps[i].function_name !== '_model_call_step') {
      i++
      continue
    }

    const llmStep = steps[i]
    i++

    const toolSteps: StepWithTiming[] = []
    while (i < steps.length && steps[i].function_name !== '_model_call_step') {
      toolSteps.push(steps[i])
      i++
    }

    agentTurnCount++
    const lastToolEnd =
      toolSteps.length > 0 ? toolSteps[toolSteps.length - 1].completed_at_epoch_ms : null
    const endedAtMs = lastToolEnd ?? llmStep.completed_at_epoch_ms
    const startedAtMs = llmStep.started_at_epoch_ms

    turns.push({
      turnNumber: agentTurnCount,
      kind: 'agent',
      llmStep,
      toolSteps,
      startedAtMs,
      endedAtMs,
      totalDurationMs: endedAtMs != null ? endedAtMs - startedAtMs : null,
    })
  }

  // The last agent turn with no tool steps is the final-answer turn
  if (turns.length > 0) {
    const last = turns[turns.length - 1]
    if (last.kind === 'agent' && last.toolSteps.length === 0) {
      last.kind = 'final'
    }
  }

  return turns
}
