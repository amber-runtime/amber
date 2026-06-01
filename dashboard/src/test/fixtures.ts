import type { Step, WorkflowDetail, WorkflowInfo, WorkflowStatus } from '../lib/types'

export function makeWorkflow(overrides: Partial<WorkflowInfo> = {}): WorkflowInfo {
  const recoveryAttempts = overrides.recovery_attempts ?? 1
  return {
    workflow_id: 'workflow-1234567890',
    name: 'research-assistant',
    status: 'SUCCESS',
    created_at: 1_700_000_000_000,
    updated_at: 1_700_000_002_500,
    forked_from: null,
    recovery_attempts: recoveryAttempts,
    attempts: recoveryAttempts,
    recoveries: Math.max(0, recoveryAttempts - 1),
    output: 'Done',
    queue_name: null,
    ...overrides,
  }
}

export function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    step_id: 1,
    function_name: '_model_call_step',
    event_type: 'llm_response',
    status: 'SUCCESS',
    duration_ms: 500,
    started_at_epoch_ms: 1_700_000_000_100,
    completed_at_epoch_ms: 1_700_000_000_600,
    display_started_at_epoch_ms: undefined as unknown as null,
    display_completed_at_epoch_ms: undefined as unknown as null,
    display_duration_ms: undefined as unknown as null,
    step_output: null,
    agent_name: 'Researcher',
    llm_model: 'gpt-4o-mini',
    tokens_in: 100,
    tokens_out: 50,
    llm_input: null,
    llm_output: null,
    tool_name: null,
    tool_args: null,
    tool_result: null,
    ...overrides,
  }
}

export function makeToolStep(overrides: Partial<Step> = {}): Step {
  return makeStep({
    step_id: 2,
    function_name: 'search_web',
    event_type: 'tool_call',
    llm_model: null,
    tokens_in: null,
    tokens_out: null,
    tool_name: 'search_web',
    tool_args: { query: 'dbos' },
    tool_result: 'Search results',
    ...overrides,
  })
}

export function makeDetail(
  overrides: {
    workflow?: Partial<WorkflowInfo>
    steps?: Step[]
    status?: WorkflowStatus
  } = {},
): WorkflowDetail {
  return {
    workflow: makeWorkflow({
      status: overrides.status,
      ...overrides.workflow,
    }),
    steps: overrides.steps ?? [makeStep(), makeToolStep()],
  }
}
