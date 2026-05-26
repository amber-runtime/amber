import type { WorkflowSummary, WorkflowDetail, WorkflowListPage, WorkflowInfo, QueuedWorkflowSummary, QueuedWorkflowListPage, PricingResponse } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// DBOS's recovery_attempts is "times attempted" (1 = ran once, no recovery).
// Derive the user-facing "times recovered" once here so render sites don't
// need to know the off-by-one.
function withRecoveries<T extends { recovery_attempts: number | null }>(
  w: T,
): T & { recoveries: number } {
  return { ...w, recoveries: Math.max(0, (w.recovery_attempts ?? 1) - 1) }
}

type RawWorkflowSummary = Omit<WorkflowSummary, 'recoveries'>
type RawWorkflowInfo = Omit<WorkflowInfo, 'recoveries'>

export async function fetchWorkflows(
  options: { limit?: number; offset?: number } = {},
): Promise<WorkflowListPage> {
  const params = new URLSearchParams()
  if (options.limit != null) params.set('limit', String(options.limit))
  if (options.offset != null) params.set('offset', String(options.offset))
  const qs = params.toString()
  const res = await fetch(`${API_BASE}/workflows${qs ? `?${qs}` : ''}`)
  const raw = await handleResponse<{
    workflows: RawWorkflowSummary[]
    has_more: boolean
  }>(res)
  return {
    workflows: raw.workflows.map(withRecoveries),
    hasMore: raw.has_more,
  }
}

export async function fetchWorkflowDetail(id: string): Promise<WorkflowDetail> {
  const res = await fetch(`${API_BASE}/workflows/${encodeURIComponent(id)}`)
  const raw = await handleResponse<{
    workflow: RawWorkflowInfo
    steps: WorkflowDetail['steps']
    events: unknown[]
  }>(res)
  return { workflow: withRecoveries(raw.workflow), steps: raw.steps }
}

export async function resumeWorkflow(workflowId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/workflows/${encodeURIComponent(workflowId)}/resume`,
    { method: 'POST' },
  )
  await handleResponse<unknown>(res)
}

export async function cancelWorkflow(workflowId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/workflows/${encodeURIComponent(workflowId)}/cancel`,
    { method: 'POST' },
  )
  await handleResponse<unknown>(res)
}

export async function fetchPricing(): Promise<PricingResponse> {
  const res = await fetch(`${API_BASE}/pricing`)
  return handleResponse<PricingResponse>(res)
}

export async function fetchQueuedWorkflows(
  options: { limit?: number; offset?: number; queueName?: string } = {},
): Promise<QueuedWorkflowListPage> {
  const params = new URLSearchParams()
  if (options.limit != null) params.set('limit', String(options.limit))
  if (options.offset != null) params.set('offset', String(options.offset))
  if (options.queueName != null) params.set('queue_name', options.queueName)
  const qs = params.toString()
  const res = await fetch(`${API_BASE}/queued-workflows${qs ? `?${qs}` : ''}`)
  const raw = await handleResponse<{ workflows: QueuedWorkflowSummary[]; has_more: boolean }>(res)
  return { workflows: raw.workflows, hasMore: raw.has_more }
}
