export type WorkflowStatus = 'SUCCESS' | 'PENDING' | 'ERROR' | 'CANCELLED' | 'ENQUEUED'

export interface Step {
  step_id: number | null
  function_name: string | null
  event_type: string
  status: 'SUCCESS' | 'ERROR'
  duration_ms: number | null
  started_at_epoch_ms: number | null
  completed_at_epoch_ms: number | null
  step_output: unknown | null
  agent_name: string | null
  llm_model: string | null
  tokens_in: number | null
  tokens_out: number | null
  llm_input: unknown[] | null
  llm_output: unknown[] | null
  tool_name: string | null
  tool_args: unknown
  tool_result: string | null
}

export interface WorkflowInfo {
  workflow_id: string
  name: string
  status: WorkflowStatus
  created_at: number
  updated_at: number
  recovery_attempts: number | null   // raw DBOS counter; 1 = first run, no recovery
  recoveries: number                 // derived: max(0, recovery_attempts - 1)
  output: string | null
}

export interface WorkflowDetail {
  workflow: WorkflowInfo
  steps: Step[]
}

export interface WorkflowSummary {
  workflow_id: string
  name: string
  status: WorkflowStatus
  created_at: number
  completed_at: number
  recovery_attempts: number | null   // raw DBOS counter; 1 = first run, no recovery
  recoveries: number                 // derived: max(0, recovery_attempts - 1)
}

export interface AgentGroup {
  agentName: string | null   // null = preflight infrastructure steps
  steps: Step[]
  startedAtMs: number | null
  endedAtMs: number | null
  totalDurationMs: number | null
}

export interface QueuedWorkflowSummary {
  workflow_id: string
  name: string
  status: WorkflowStatus
  created_at: number | null
  queue_name: string | null
}

export interface QueuedWorkflowListPage {
  workflows: QueuedWorkflowSummary[]
  hasMore: boolean
}

export type SelectedStepId = number | null

export interface WorkflowListPage {
  workflows: WorkflowSummary[]
  hasMore: boolean
}

export interface ModelPricing {
  input: number
  output: number
  cache_read: number | null
  cache_creation: number | null
}

export interface PricingResponse {
  models: Record<string, ModelPricing>
  synced_at: number | null
  error?: string
}
