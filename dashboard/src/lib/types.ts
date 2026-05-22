export type WorkflowStatus = 'SUCCESS' | 'PENDING' | 'ERROR' | 'CANCELLED'

export interface Agent {
  name: string
}

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
  recovery_attempts: number | null
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
  recovery_attempts: number | null
}

export interface AgentGroup {
  agentName: string | null   // null = preflight infrastructure steps
  steps: Step[]
  startedAtMs: number | null
  endedAtMs: number | null
  totalDurationMs: number | null
}
