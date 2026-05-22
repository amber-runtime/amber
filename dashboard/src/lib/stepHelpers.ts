import type { Step, AgentGroup } from './types'

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
