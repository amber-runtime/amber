import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setPricing } from './pricingStore'
import {
  computeDowntimeBarGeometry,
  computeWorkflowWindow,
  computeCostBreakdown,
  countLlmCalls,
  countToolCalls,
  errorDowntimeInterval,
  findLargestRecoveryGap,
  formatCost,
  groupStepsByAgent,
  humanizeStepName,
  humanizeWorkflowName,
  isWorkflowActivelyRunning,
  pendingStallDowntimeInterval,
  recoveryDowntimeInterval,
  sumTokens,
  sumTokensIn,
  sumTokensOut,
} from './stepHelpers'
import { makeStep, makeToolStep, makeWorkflow } from '../test/fixtures'

describe('stepHelpers', () => {
  beforeEach(() => {
    setPricing({}, null)
  })

  it('humanizes known and slugged names', () => {
    expect(humanizeStepName('_model_call_step')).toBe('Agent Turn')
    expect(humanizeStepName('search_public_sources')).toBe('Search Public Sources')
    expect(humanizeStepName(null)).toBe('Unknown')
    expect(humanizeWorkflowName('research-assistant')).toBe('Research Assistant')
    expect(humanizeWorkflowName('run_agent')).toBe('Research Agent')
  })

  it('sums tokens and counts llm/tool rows by event type', () => {
    const steps = [
      makeStep({ tokens_in: 10, tokens_out: 5 }),
      makeToolStep({ tokens_in: null, tokens_out: null }),
      makeStep({
        step_id: 3,
        event_type: 'step',
        function_name: 'search_web',
        tool_name: 'search_web',
        tokens_in: 7,
        tokens_out: null,
      }),
    ]

    expect(sumTokens(steps)).toBe(22)
    expect(sumTokensIn(steps)).toBe(17)
    expect(sumTokensOut(steps)).toBe(5)
    expect(countLlmCalls(steps)).toBe(1)
    expect(countToolCalls(steps)).toBe(1)
  })

  it('formats cost and includes unknown models in breakdown without pricing', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    setPricing(
      {
        'gpt-4o-mini': {
          input: 0.00000015,
          output: 0.0000006,
          cache_read: null,
          cache_creation: null,
        },
      },
      null,
    )

    const breakdown = computeCostBreakdown([
      makeStep({ llm_model: 'gpt-4o-mini', tokens_in: 1_000, tokens_out: 500 }),
      makeStep({ step_id: 2, llm_model: 'unknown-model', tokens_in: 10, tokens_out: 10 }),
    ])

    expect(formatCost(null)).toBe('—')
    expect(formatCost(0.00045)).toBe('<$0.01')
    expect(formatCost(1.234)).toBe('$1.23')
    expect(breakdown).toEqual([
      expect.objectContaining({
        model: 'gpt-4o-mini',
        inputTokens: 1_000,
        outputTokens: 500,
        subtotal: 0.00045,
      }),
      expect.objectContaining({
        model: 'unknown-model',
        inputRate: null,
        subtotal: null,
      }),
    ])
    expect(warn).toHaveBeenCalledWith('No pricing entry for model: unknown-model')
  })

  it('groups steps by agent and attaches infrastructure after an agent starts', () => {
    const groups = groupStepsByAgent([
      makeStep({
        step_id: 1,
        agent_name: null,
        started_at_epoch_ms: 100,
        completed_at_epoch_ms: 200,
      }),
      makeStep({
        step_id: 2,
        agent_name: 'Planner',
        started_at_epoch_ms: 250,
        completed_at_epoch_ms: 300,
      }),
      makeStep({
        step_id: 3,
        agent_name: null,
        function_name: 'DBOS.sleep',
        started_at_epoch_ms: 325,
        completed_at_epoch_ms: 400,
      }),
      makeStep({
        step_id: 4,
        agent_name: 'Writer',
        started_at_epoch_ms: 500,
        completed_at_epoch_ms: 700,
      }),
    ])

    expect(groups).toHaveLength(3)
    expect(groups[0]).toEqual(expect.objectContaining({ agentName: null }))
    expect(groups[0].steps.map((s) => s.step_id)).toEqual([1])
    expect(groups[1]).toEqual(expect.objectContaining({ agentName: 'Planner' }))
    expect(groups[1].steps.map((s) => s.step_id)).toEqual([2, 3])
    expect(groups[2]).toEqual(expect.objectContaining({ agentName: 'Writer' }))
  })

  it('finds the largest recovery gap without treating overlapping work as idle', () => {
    const steps = [
      makeStep({ step_id: 1, started_at_epoch_ms: 0, completed_at_epoch_ms: 1_000 }),
      makeStep({ step_id: 2, started_at_epoch_ms: 500, completed_at_epoch_ms: 2_000 }),
      makeStep({ step_id: 3, started_at_epoch_ms: 3_500, completed_at_epoch_ms: 4_000 }),
      makeStep({ step_id: 4, started_at_epoch_ms: 6_500, completed_at_epoch_ms: 7_000 }),
    ]

    expect(findLargestRecoveryGap(steps)).toEqual({ start: 4_000, end: 6_500 })
  })

  it('accepts workflow fixtures with typed statuses', () => {
    expect(makeWorkflow({ status: 'ERROR' }).status).toBe('ERROR')
  })

  it('only treats pending workflows as actively running', () => {
    expect(isWorkflowActivelyRunning('PENDING')).toBe(true)
    expect(isWorkflowActivelyRunning('SUCCESS')).toBe(false)
    expect(isWorkflowActivelyRunning('ERROR')).toBe(false)
    expect(isWorkflowActivelyRunning('CANCELLED')).toBe(false)
    expect(isWorkflowActivelyRunning('MAX_RECOVERY_ATTEMPTS_EXCEEDED')).toBe(false)
  })

  it('can extend workflow windows with a visual end override', () => {
    vi.useFakeTimers()
    vi.setSystemTime(10_000)

    expect(
      computeWorkflowWindow(
        makeWorkflow({
          status: 'ERROR',
          created_at: 0,
          updated_at: 4_000,
        }),
        [],
        8_000,
      ),
    ).toEqual({ start: 0, end: 8_000 })
  })

  it('converts downtime intervals into clipped gantt geometry', () => {
    expect(
      computeDowntimeBarGeometry(
        { start: 2_000, end: 6_000, source: 'refresh' },
        0,
        10_000,
        10_000,
      ),
    ).toEqual({ leftPct: 20, widthPct: 40 })

    expect(
      computeDowntimeBarGeometry(
        { start: -1_000, end: null, source: 'error' },
        0,
        10_000,
        5_000,
      ),
    ).toEqual({ leftPct: 0, widthPct: 50 })
  })

  it('derives recovered crash gaps as red downtime intervals', () => {
    const workflow = makeWorkflow({ attempts: 2, recovery_attempts: 2 })
    const steps = [
      makeStep({ step_id: 1, started_at_epoch_ms: 0, completed_at_epoch_ms: 1_000 }),
      makeStep({ step_id: 2, started_at_epoch_ms: 6_000, completed_at_epoch_ms: 7_000 }),
    ]

    expect(recoveryDowntimeInterval(workflow, steps)).toEqual({
      start: 1_000,
      end: 6_000,
      source: 'recovery',
      anchorStepId: 1,
    })
  })

  it('derives active and recovered error downtime intervals from failed steps', () => {
    const erroredSteps = [
      makeStep({
        step_id: 1,
        status: 'ERROR',
        started_at_epoch_ms: 2_000,
        completed_at_epoch_ms: 2_500,
      }),
    ]

    expect(
      errorDowntimeInterval(
        makeWorkflow({ status: 'ERROR', updated_at: 2_500 }),
        erroredSteps,
      ),
    ).toEqual({ start: 2_000, end: null, source: 'error', anchorStepId: 1 })

    expect(
      errorDowntimeInterval(
        makeWorkflow({ status: 'PENDING', updated_at: 8_000 }),
        [
          ...erroredSteps,
          makeStep({
            step_id: 2,
            started_at_epoch_ms: 5_000,
            completed_at_epoch_ms: 6_000,
          }),
        ],
      ),
    ).toEqual({ start: 2_000, end: 5_000, source: 'error', anchorStepId: 1 })
  })

  it('derives pending-stall downtime only after the grace period', () => {
    const workflow = makeWorkflow({ status: 'PENDING' })
    const steps = [
      makeStep({
        step_id: 1,
        started_at_epoch_ms: 0,
        completed_at_epoch_ms: 2_000,
      }),
      makeStep({
        step_id: 2,
        started_at_epoch_ms: 2_500,
        completed_at_epoch_ms: 4_000,
      }),
    ]

    expect(pendingStallDowntimeInterval(workflow, steps, 8_999)).toBeNull()
    expect(pendingStallDowntimeInterval(workflow, steps, 9_000)).toEqual({
      start: 4_000,
      end: null,
      source: 'pending-stall',
      anchorStepId: 2,
    })
  })

  it('does not derive pending-stall downtime for non-pending or currently active steps', () => {
    expect(
      pendingStallDowntimeInterval(
        makeWorkflow({ status: 'SUCCESS' }),
        [
          makeStep({
            step_id: 1,
            started_at_epoch_ms: 0,
            completed_at_epoch_ms: 1_000,
          }),
        ],
        10_000,
      ),
    ).toBeNull()

    expect(
      pendingStallDowntimeInterval(
        makeWorkflow({ status: 'PENDING' }),
        [
          makeStep({
            step_id: 1,
            started_at_epoch_ms: 0,
            completed_at_epoch_ms: null,
            display_completed_at_epoch_ms: undefined as unknown as null,
          }),
        ],
        10_000,
      ),
    ).toBeNull()
  })
})
