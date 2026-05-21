import type { Step, WorkflowInfo, WorkflowSummary, WorkflowDetail, LLMOutput } from './types'
import type { AgentDef } from './agentRegistry'

export interface RunnerFns {
  updateSummary: (id: string, patch: Partial<WorkflowSummary>) => void
  setDetail: (id: string, detail: WorkflowDetail) => void
}

// ─── Mock output generators ──────────────────────────────────────────────────

function makeLLMToolCallOutput(topic: string, turn: number): LLMOutput {
  const queries = [
    `${topic} overview and fundamentals`,
    `${topic} practical applications 2026`,
  ]
  return {
    model: 'gpt-5.4-mini-2026-03-17',
    output: [
      {
        type: 'function_call',
        arguments: JSON.stringify({ query: queries[(turn - 1) % queries.length] }),
        call_id: `call_m${turn}_${Math.random().toString(16).slice(2, 6)}`,
        name: 'search_web',
        id: `fc_m${turn}`,
        status: 'completed',
      },
    ],
    usage: {
      requests: 1,
      input_tokens: 155 + (turn - 1) * 340,
      output_tokens: 28 + turn * 4,
      total_tokens: 183 + (turn - 1) * 344,
    },
    response_id: `resp_mock_${Math.random().toString(16).slice(2, 12)}`,
    request_id: `req_mock_t${turn}`,
  }
}

function makeSearchWebOutput(topic: string, turn: number): string {
  const results = [
    {
      title: `${topic} — Concepts and Architecture`,
      url: `https://example.com/${topic.toLowerCase().replace(/\s+/g, '-')}-concepts`,
      summary: `A comprehensive overview of ${topic}, covering core concepts, design patterns, and how leading teams implement this in production systems.`,
    },
    {
      title: `${topic} in Practice: ${turn === 1 ? 'Getting Started' : 'Advanced Patterns'}`,
      url: `https://docs.example.com/${topic.toLowerCase().replace(/\s+/g, '-')}-guide-${turn}`,
      summary: `Practical guide to ${topic} with real-world examples, performance benchmarks, and common pitfalls to avoid.`,
    },
  ]
  return results
    .map((r) => `Title: ${r.title}\nURL: ${r.url}\nSummary: ${r.summary}`)
    .join('\n---\n')
}

const WEATHER_CONDITIONS = [
  { desc: 'Partly cloudy', wind: 'light winds from the southwest', precip: 'No precipitation expected' },
  { desc: 'Mostly sunny', wind: 'calm winds', precip: 'No precipitation expected' },
  { desc: 'Overcast', wind: 'moderate winds from the northwest', precip: 'Slight chance of showers later' },
  { desc: 'Clear skies', wind: 'gentle breeze from the east', precip: 'No precipitation expected' },
  { desc: 'Mostly cloudy', wind: 'light winds from the north', precip: 'Isolated showers possible' },
]

function makeWeatherAnswer(location: string): string {
  const cond = WEATHER_CONDITIONS[Math.floor(Math.random() * WEATHER_CONDITIONS.length)]
  const tempF = 55 + Math.floor(Math.random() * 35)
  const highF = tempF + 4 + Math.floor(Math.random() * 8)
  const humidity = 40 + Math.floor(Math.random() * 40)
  return `## Weather Report: ${location}\n\nCurrently **${tempF}°F** in ${location}. ${cond.desc} with ${cond.wind}.\n\nExpected high of **${highF}°F** today. ${cond.precip}. Humidity at ${humidity}%.`
}

function makeFinalLLMOutput(topic: string, agentId: string): LLMOutput {
  const answer = agentId === 'weather_agent'
    ? makeWeatherAnswer(topic)
    : `## ${topic}\n\nResearch complete. Here is a summary of findings:\n\n### Key Concepts\n\n- **Core idea**: ${topic} addresses a fundamental challenge in modern software systems\n- **Adoption**: Widely adopted across the industry with multiple mature implementations\n- **Trade-offs**: Each approach optimizes for different constraints — latency, consistency, or operational simplicity\n\n### Comparison\n\n| Approach | Strengths | Weaknesses |\n|----------|-----------|------------|\n| Option A | Simple, proven | Limited at scale |\n| Option B | High performance | Operational complexity |\n| Option C | Flexible | Higher resource cost |\n\n### Recommendations\n\nStart with the simplest option that satisfies your requirements. Introduce complexity only when you have measured a concrete bottleneck that simpler approaches cannot solve.`
  return {
    model: 'gpt-5.4-mini-2026-03-17',
    output: [
      {
        type: 'message',
        id: 'msg_mock_final',
        content: [{ text: answer, type: 'output_text', annotations: [], logprobs: [] }],
        role: 'assistant',
        status: 'completed',
        phase: 'final_answer',
      },
    ],
    usage: { requests: 1, input_tokens: 1180, output_tokens: 395, total_tokens: 1575 },
    response_id: `resp_mock_final_${Math.random().toString(16).slice(2, 12)}`,
    request_id: 'req_mock_final',
  }
}

// ─── Chain runner ─────────────────────────────────────────────────────────────
// Each step fires after the previous step completes. `delay` is a thunk so each
// step can use a different jitter profile — wide for step durations, tiny for
// inter-step handoffs. This keeps bars nearly contiguous in the Gantt, making
// the recovery stall the only obviously large gap.

type ChainStep = { delay: () => number; fn: () => void }

function runChain(steps: ChainStep[]): void {
  let i = 0
  const next = () => {
    if (i >= steps.length) return
    const { delay, fn } = steps[i++]
    setTimeout(() => {
      fn()
      next()
    }, delay())
  }
  next()
}

// ±400ms jitter on step durations (LLM inference, tool execution, initial wait)
const dur =
  (base: number): (() => number) =>
  () =>
    Math.max(200, base + Math.floor((Math.random() - 0.5) * 800))

// 50–150ms for the handoff between steps — nearly contiguous in the Gantt
const gap: () => number = () => 50 + Math.floor(Math.random() * 100)

// ─── Public API ───────────────────────────────────────────────────────────────

export function runMockWorkflow(
  workflowId: string,
  agentDef: AgentDef,
  topic: string,
  fns: RunnerFns,
): void {
  const { updateSummary, setDetail } = fns
  const startMs = Date.now()
  const isRecoveryRun = Math.random() < 0.3

  let idCounter = 1
  let info: WorkflowInfo = {
    workflow_id: workflowId,
    name: agentDef.id,
    status: 'PENDING',
    created_at: startMs,
    updated_at: startMs,
    recovery_attempts: null,
    input: `{'args': ('${topic}',), 'kwargs': {}}`,
  }
  const steps: Step[] = []

  const flush = () => setDetail(workflowId, { workflow: info, steps: [...steps] })

  const pushStep = (name: string) => {
    steps.push({
      function_id: idCounter++,
      function_name: name,
      output: null,
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: Date.now(),
      completed_at_epoch_ms: null,
    })
    info = { ...info, updated_at: Date.now() }
    flush()
    updateSummary(workflowId, { step_count: steps.length, updated_at: info.updated_at })
  }

  const completeLast = (output: Step['output'], error: string | null = null) => {
    const idx = steps.length - 1
    steps[idx] = { ...steps[idx], output, error, completed_at_epoch_ms: Date.now() }
    info = { ...info, updated_at: Date.now() }
    flush()
    updateSummary(workflowId, { updated_at: info.updated_at })
  }

  const patchInfo = (patch: Partial<WorkflowInfo>, summaryPatch?: Partial<WorkflowSummary>) => {
    info = { ...info, ...patch, updated_at: Date.now() }
    flush()
    if (summaryPatch) updateSummary(workflowId, { ...summaryPatch, updated_at: info.updated_at })
  }

  // ── Timing constants (base ms, before jitter) ─────────────────────────────
  // Normal: ~17s total.  Step appearances ≈ 1.8s / 4.8s / 7.8s / 10.8s / 13.8s.
  // Recovery: ~19.5s total, with a 2.5s stall gap that dwarfs every inter-step gap.
  const INITIAL       = 1800 // start → first step visible
  const LLM_COMPLETE  = 2900 // LLM inference duration
  const TOOL_COMPLETE = 2900 // tool execution duration
  const FINAL_COMPLETE = 3200 // final LLM duration (slightly longer)
  const STALL         = 2500 // recovery: silent window while process is down

  if (!isRecoveryRun) {
    // ── Normal run (~17s, 5 steps) ─────────────────────────────────────────
    //
    // dur(…) — step duration, ±400ms jitter
    // gap    — inter-step handoff, 50–150ms (nearly contiguous in the Gantt)

    runChain([
      { delay: dur(INITIAL),        fn: () => pushStep('_model_call_step') },
      { delay: dur(LLM_COMPLETE),   fn: () => completeLast(makeLLMToolCallOutput(topic, 1)) },
      { delay: gap,                 fn: () => pushStep('search_web') },
      { delay: dur(TOOL_COMPLETE),  fn: () => completeLast(makeSearchWebOutput(topic, 1)) },
      { delay: gap,                 fn: () => pushStep('_model_call_step') },
      { delay: dur(LLM_COMPLETE),   fn: () => completeLast(makeLLMToolCallOutput(topic, 2)) },
      { delay: gap,                 fn: () => pushStep('search_web') },
      { delay: dur(TOOL_COMPLETE),  fn: () => completeLast(makeSearchWebOutput(topic, 2)) },
      { delay: gap,                 fn: () => pushStep('_model_call_step') },
      {
        delay: dur(FINAL_COMPLETE),
        fn: () => {
          completeLast(makeFinalLLMOutput(topic, agentDef.id))
          patchInfo({ status: 'SUCCESS' }, { status: 'SUCCESS' })
        },
      },
    ])
  } else {
    // ── Recovery run (~19.5s, 5 steps) ────────────────────────────────────
    //
    // DBOS recovery: a crashed workflow stays PENDING. On restart, DBOS scans
    // for PENDING workflows and resumes them; completed steps are replayed from
    // the DB (not re-executed). The UI shows exactly two signals:
    //   1. A visible gap in the Gantt — bars stop while the process is down
    //   2. recovery_attempts → 1, making the "Recovered 1×" pill appear
    //
    // Everything else is unchanged. No red step, no status transition, no flicker.
    // The stall (~2.5s) is 20-30× larger than any inter-step gap (50–150ms),
    // so it reads as the one obvious break in an otherwise tight timeline.

    runChain([
      { delay: dur(INITIAL),        fn: () => pushStep('_model_call_step') },
      { delay: dur(LLM_COMPLETE),   fn: () => completeLast(makeLLMToolCallOutput(topic, 1)) },
      { delay: gap,                 fn: () => pushStep('search_web') },
      { delay: dur(TOOL_COMPLETE),  fn: () => completeLast(makeSearchWebOutput(topic, 1)) },
      // ── crash window ── process is down; no steps, no state change, just silence
      {
        delay: dur(STALL),
        fn: () => patchInfo({ recovery_attempts: 1 }, { recovery_attempts: 1 }),
      },
      // ── resumed ── previously completed steps are not re-executed
      { delay: gap,                 fn: () => pushStep('_model_call_step') },
      { delay: dur(LLM_COMPLETE),   fn: () => completeLast(makeLLMToolCallOutput(topic, 2)) },
      { delay: gap,                 fn: () => pushStep('search_web') },
      { delay: dur(TOOL_COMPLETE),  fn: () => completeLast(makeSearchWebOutput(topic, 2)) },
      { delay: gap,                 fn: () => pushStep('_model_call_step') },
      {
        delay: dur(FINAL_COMPLETE),
        fn: () => {
          completeLast(makeFinalLLMOutput(topic, agentDef.id))
          patchInfo({ status: 'SUCCESS' }, { status: 'SUCCESS' })
        },
      },
    ])
  }
}
