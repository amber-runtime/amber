import type { WorkflowSummary, WorkflowDetail } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export async function fetchWorkflows(): Promise<WorkflowSummary[]> {
  const res = await fetch(`${API_BASE}/workflows`)
  return handleResponse(res)
}

export async function fetchWorkflowDetail(id: string): Promise<WorkflowDetail> {
  const res = await fetch(`${API_BASE}/workflows/${encodeURIComponent(id)}`)
  const raw = await handleResponse<{
    workflow: WorkflowDetail['workflow']
    steps: WorkflowDetail['steps']
    events: unknown[]
  }>(res)
  return { workflow: raw.workflow, steps: raw.steps }
}
