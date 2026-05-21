export type WorkflowStatus = 'SUCCESS' | 'PENDING' | 'ERROR' | 'CANCELLED'

export interface LLMFunctionCallItem {
  type: 'function_call'
  arguments: string
  call_id: string
  name: string
  id: string
  status: string
}

export interface LLMContentItem {
  text: string
  type: string
  annotations: unknown[]
  logprobs: unknown[]
}

export interface LLMMessageItem {
  type: 'message'
  id: string
  content: LLMContentItem[]
  role: string
  status: string
  phase?: string
}

export type LLMOutputItem = LLMFunctionCallItem | LLMMessageItem

export interface LLMUsage {
  requests: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
}

export interface LLMOutput {
  output: LLMOutputItem[]
  usage: LLMUsage
  response_id: string
  request_id: string
  model?: string
}

export interface Step {
  function_id: number
  function_name: string
  output: LLMOutput | string | null
  error: string | null
  child_workflow_id: string | null
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
  input?: string
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
  updated_at: number
  recovery_attempts: number | null
  step_count: number
  input?: string
}

export type TurnKind = 'preflight' | 'agent' | 'final'

export interface Turn {
  turnNumber: number        // 1-indexed for agent/final; 0 for preflight
  kind: TurnKind
  llmStep: Step | null      // null only for preflight
  toolSteps: Step[]
  startedAtMs: number
  endedAtMs: number | null  // null if any step is still running
  totalDurationMs: number | null
}
