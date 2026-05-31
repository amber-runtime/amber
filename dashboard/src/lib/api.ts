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
// Preserve that raw value for UI labels and also keep the old recoveries derivation
// for visualizations that specifically mean "auto-recovered after failure".
function withAttempts<T extends { recovery_attempts: number | null }>(
  w: T,
): T & { attempts: number | null; recoveries: number } {
  const attempts = w.recovery_attempts
  return { ...w, attempts, recoveries: Math.max(0, (attempts ?? 1) - 1) }
}

type RawWorkflowSummary = Omit<WorkflowSummary, 'attempts' | 'recoveries'>
type RawWorkflowInfo = Omit<WorkflowInfo, 'attempts' | 'recoveries'>
type RawQueuedWorkflowSummary = Omit<QueuedWorkflowSummary, 'attempts'>

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
    workflows: raw.workflows.map(withAttempts),
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
  return { workflow: withAttempts(raw.workflow), steps: raw.steps }
}

export async function resumeWorkflow(workflowId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/workflows/${encodeURIComponent(workflowId)}/resume`,
    { method: 'POST' },
  )
  await handleResponse<unknown>(res)
}

export async function deleteWorkflows(workflowIds: string[]): Promise<void> {
  const res = await fetch(`${API_BASE}/workflows/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow_ids: workflowIds }),
  })
  await handleResponse<unknown>(res)
}

export async function cancelWorkflow(workflowId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/workflows/${encodeURIComponent(workflowId)}/cancel`,
    { method: 'POST' },
  )
  await handleResponse<unknown>(res)
}

export async function forkWorkflow(
  workflowId: string,
  startStep: number,
): Promise<{ workflowId: string; forkedWorkflowId: string; startStep: number }> {
  const res = await fetch(
    `${API_BASE}/workflows/${encodeURIComponent(workflowId)}/fork`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start_step: startStep }),
    },
  )
  const raw = await handleResponse<{
    workflow_id: string
    forked_workflow_id: string
    start_step: number
  }>(res)
  return {
    workflowId: raw.workflow_id,
    forkedWorkflowId: raw.forked_workflow_id,
    startStep: raw.start_step,
  }
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
  const raw = await handleResponse<{ workflows: RawQueuedWorkflowSummary[]; has_more: boolean }>(res)
  return { workflows: raw.workflows.map(withAttempts), hasMore: raw.has_more }
}
