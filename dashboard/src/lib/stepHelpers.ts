import type { Step, LLMOutput, LLMMessageItem, Turn } from './types'

export type StepKind = 'llm' | 'tool' | 'sleep' | 'other'

export function humanizeStepName(functionName: string): string {
  const map: Record<string, string> = {
    _model_call_step: 'Agent Turn',
    search_web: 'Web Search',
    'DBOS.sleep': 'Sleep',
  }
  if (map[functionName]) return map[functionName]
  return functionName
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function humanizeWorkflowName(name: string): string {
  const map: Record<string, string> = {
    run_agent: 'Research Agent',
    run_email_campaign: 'Email Campaign',
  }
  return map[name] ?? humanizeStepName(name)
}

export function getStepKind(functionName: string): StepKind {
  if (functionName === '_model_call_step') return 'llm'
  if (functionName === 'DBOS.sleep') return 'sleep'
  // A step wrapped with @step() that isn't a DBOS internal is a user tool
  return 'tool'
}

export function isLLMOutput(output: unknown): output is LLMOutput {
  return (
    typeof output === 'object' &&
    output !== null &&
    'output' in output &&
    Array.isArray((output as LLMOutput).output)
  )
}

export function extractFinalAnswer(steps: Step[]): string | null {
  const llmSteps = [...steps]
    .filter((s) => s.function_name === '_model_call_step')
    .reverse()

  for (const step of llmSteps) {
    if (!isLLMOutput(step.output)) continue
    for (const item of step.output.output) {
      if (item.type === 'message') {
        const msg = item as LLMMessageItem
        const text = msg.content?.[0]?.text
        if (text) return text
      }
    }
  }
  return null
}

export function extractWorkflowInputArg(input: string | null | undefined): string {
  if (!input) return '(no input)'
  // Python repr: {'args': ('durable execution',), 'kwargs': {}}
  const match = input.match(/['"]args['"]\s*:\s*\(?['"]([^'"]+)['"]/)
  if (match) return match[1]
  // JSON format: {"args": ["some topic"]}
  try {
    const parsed = JSON.parse(input.replace(/'/g, '"')) as { args?: unknown[] }
    if (Array.isArray(parsed.args) && parsed.args.length > 0) {
      return String(parsed.args[0])
    }
  } catch {
    // fall through
  }
  return input
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

export function sumTokens(steps: Step[]): number {
  return steps.reduce((sum, step) => {
    if (!isLLMOutput(step.output)) return sum
    return sum + (step.output.usage?.total_tokens ?? 0)
  }, 0)
}

export function groupStepsIntoTurns(steps: Step[]): Turn[] {
  const turns: Turn[] = []
  let i = 0
  let agentTurnCount = 0

  // Collect preflight steps (before the first _model_call_step)
  const preflightSteps: Step[] = []
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
      // Orphan tool step between turns — absorb and skip
      i++
      continue
    }

    const llmStep = steps[i]
    i++

    const toolSteps: Step[] = []
    while (i < steps.length && steps[i].function_name !== '_model_call_step') {
      toolSteps.push(steps[i])
      i++
    }

    agentTurnCount++
    const lastToolEnd = toolSteps.length > 0
      ? toolSteps[toolSteps.length - 1].completed_at_epoch_ms
      : null
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

export function stepDurationMs(step: Step): number | null {
  if (step.completed_at_epoch_ms == null) return null
  return step.completed_at_epoch_ms - step.started_at_epoch_ms
}
