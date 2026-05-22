import type { WorkflowSummary, WorkflowDetail, Agent } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string
const CUSTOMER_APP = import.meta.env.VITE_CUSTOMER_APP_URL as string

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

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${CUSTOMER_APP}/agents`)
  return handleResponse(res)
}

export async function triggerWorkflow(
  agent: string,
  input: string,
  crashDemo?: boolean,
): Promise<{ workflow_id: string; agent: string }> {
  const url = new URL(`${CUSTOMER_APP}/runs`)
  if (crashDemo) url.searchParams.set('crash_during_hotel', 'true')
  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent, input }),
  })
  return handleResponse(res)
}
