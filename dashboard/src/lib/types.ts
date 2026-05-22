export type WorkflowStatus = 'SUCCESS' | 'PENDING' | 'ERROR' | 'CANCELLED'

export interface Agent {
  name: string
}

// Step record as returned by GET /workflows/{id} — no per-step timestamps in the backend.
export interface Step {
  step_id: number | null
  function_name: string | null
  status: 'SUCCESS' | 'ERROR'
  duration_ms: number | null
  error: string | null
  llm_model: string | null
  tokens_in: number | null
  tokens_out: number | null
  provider_response_id: string | null
  llm_input: unknown[] | null
  llm_output: unknown[] | null
  tool_name: string | null
  tool_args: unknown
  tool_match_status: string | null
}

// Step enriched client-side with synthetic timestamps derived from cumulative duration_ms.
// These are NOT from the backend — they assume steps execute consecutively with no gap.
// Bars on the Gantt will be slightly compressed relative to wall-clock time because
// inter-step orchestration time (workflow function execution between steps) is not captured.
// DBOS.sleep steps are correctly represented since their sleep duration IS in duration_ms.
export interface StepWithTiming extends Step {
  started_at_epoch_ms: number
  completed_at_epoch_ms: number | null
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
  steps: StepWithTiming[]
}

export interface WorkflowSummary {
  workflow_id: string
  name: string
  status: WorkflowStatus
  created_at: number
  completed_at: number
  recovery_attempts: number | null
}

export type TurnKind = 'preflight' | 'agent' | 'final'

export interface Turn {
  turnNumber: number
  kind: TurnKind
  llmStep: StepWithTiming | null
  toolSteps: StepWithTiming[]
  startedAtMs: number
  endedAtMs: number | null
  totalDurationMs: number | null
}
