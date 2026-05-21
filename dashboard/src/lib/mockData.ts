import type { WorkflowDetail, WorkflowSummary } from './types'

// ── SUCCESS fixture — 7 steps, 2 web searches, final answer ──────────────────

export const mockWorkflowSuccess: WorkflowDetail = {
  workflow: {
    workflow_id: '019e3c95-08de-7451-af78-01a1f83c43bb',
    name: 'run_agent',
    status: 'SUCCESS',
    created_at: 1779132860641,
    updated_at: 1779132887183,
    recovery_attempts: null,
    input: "{'args': ('durable execution',), 'kwargs': {}}",
  },
  steps: [
    {
      function_id: 1,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'function_call',
            arguments: '{"query":"durable execution definition workflow engine retries"}',
            call_id: 'call_Rw1a',
            name: 'search_web',
            id: 'fc_001',
            status: 'completed',
          },
        ],
        usage: { requests: 1, input_tokens: 155, output_tokens: 31, total_tokens: 186 },
        response_id: 'resp_0afd000f28605ace006a0b7779daf4819694fc03ed5da47cfe',
        request_id: 'req_aGvp1',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779132860652,
      completed_at_epoch_ms: 1779132863071,
    },
    {
      function_id: 2,
      function_name: 'search_web',
      output:
        'Title: The definitive guide to Durable Execution - Temporal\nURL: https://temporal.io/blog/what-is-durable-execution\nSummary: Durable Execution is crash-proof execution. It enables developers to write reliable software with less effort — applications automatically resume where they left off after any failure.\n---\nTitle: What is Durable Execution? - Restate\nURL: https://restate.dev/what-is-durable-execution/\nSummary: Durable Execution is a programming paradigm that makes ordinary code resilient to crashes, restarts, and infrastructure failures by persisting execution state.',
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779132863076,
      completed_at_epoch_ms: 1779132866161,
    },
    {
      function_id: 3,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'function_call',
            arguments: '{"query":"durable execution vs message queues exactly-once semantics"}',
            call_id: 'call_Rw2b',
            name: 'search_web',
            id: 'fc_002',
            status: 'completed',
          },
        ],
        usage: { requests: 1, input_tokens: 489, output_tokens: 34, total_tokens: 523 },
        response_id: 'resp_0afd000f28605ace006a0b777e033c8196a74a867f89e9f70d',
        request_id: 'req_bHwq2',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779132866165,
      completed_at_epoch_ms: 1779132868920,
    },
    {
      function_id: 4,
      function_name: 'search_web',
      output:
        'Title: Durable Execution vs. Message Queues - Temporal Blog\nURL: https://temporal.io/blog/durable-execution-vs-queues\nSummary: Unlike message queues where you must manually track state, durable execution persists workflow state automatically. Failures trigger retries from the last checkpoint, not from the start.\n---\nTitle: Exactly-once semantics with Durable Execution - DBOS Docs\nURL: https://docs.dbos.dev/concepts/durable-execution\nSummary: DBOS achieves exactly-once semantics by recording step outputs in Postgres before returning. A step that was interrupted and retried will replay its stored result rather than re-executing.',
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779132868925,
      completed_at_epoch_ms: 1779132872480,
    },
    {
      function_id: 5,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'function_call',
            arguments: '{"query":"durable execution Temporal DBOS Inngest comparison use cases"}',
            call_id: 'call_Rw3c',
            name: 'search_web',
            id: 'fc_003',
            status: 'completed',
          },
        ],
        usage: { requests: 1, input_tokens: 967, output_tokens: 40, total_tokens: 1007 },
        response_id: 'resp_0afd000f28605ace006a0b779b3188819687831d4685287136',
        request_id: 'req_cIxr3',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779132872485,
      completed_at_epoch_ms: 1779132874930,
    },
    {
      function_id: 6,
      function_name: 'search_web',
      output:
        'Title: Temporal, Inngest, DBOS — Choosing a durable execution platform\nURL: https://inngest.com/blog/durable-execution-platforms\nSummary: All three platforms share the core idea: your code checkpoints at each step so it can resume after a crash. They differ in hosting model, language support, and how deeply they integrate with your existing infrastructure.\n---\nTitle: DBOS: Lightweight Durable Execution on Postgres\nURL: https://www.dbos.dev/blog/dbos-vs-temporal\nSummary: DBOS stores workflow state directly in Postgres rather than a proprietary store, making it easy to inspect, query, and back up workflow history alongside your application data.',
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779132874935,
      completed_at_epoch_ms: 1779132878620,
    },
    {
      function_id: 7,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'message',
            id: 'msg_001',
            content: [
              {
                text: 'Durable execution is a way to run code so that it can survive crashes, restarts, retries, and infrastructure failures without losing progress.\n\n## Core idea\n\nInstead of treating a program as a short-lived process, durable execution treats it like a **durable workflow**:\n\n- **State is persisted** — intermediate results are saved to a database after each step\n- **Progress is recorded** — the system knows exactly which steps have completed and what they returned\n- **Completed steps are not re-executed** — on recovery, the workflow replays stored results\n- **After failure, execution resumes from where it left off** — not from the beginning\n\n## How it works in practice\n\nA workflow function is divided into **steps** (also called activities or tasks depending on the platform). When a step completes, its output is checkpointed. If the process crashes mid-workflow:\n\n1. The workflow is detected as interrupted\n2. A recovery process re-executes the workflow function\n3. Each step that was already completed replays its stored result instantly\n4. Execution picks up from the first incomplete step\n\n## Key platforms\n\n| Platform | State store | Hosting |\n|----------|-------------|----------|\n| **Temporal** | Proprietary | Self-hosted or cloud |\n| **DBOS** | Postgres | Self-hosted |\n| **Inngest** | Managed | Cloud |\n\n## Why it matters for AI agents\n\nLLM calls are expensive and non-deterministic. Durable execution ensures that if an agent workflow crashes after a successful LLM call, **that call is not repeated** — the stored result is replayed instead. This makes multi-step agent pipelines both cost-efficient and reliable.',
                type: 'output_text',
                annotations: [],
                logprobs: [],
              },
            ],
            role: 'assistant',
            status: 'completed',
            phase: 'final_answer',
          },
        ],
        usage: { requests: 1, input_tokens: 1432, output_tokens: 384, total_tokens: 1816 },
        response_id: 'resp_0afd000f28605ace006a0b77a1dec881968ae34b6ef6d720c7',
        request_id: 'req_dJys4',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779132883197,
      completed_at_epoch_ms: 1779132887177,
    },
  ],
}

// ── PENDING fixture — mid-run, no final answer ────────────────────────────────

export const mockWorkflowPending: WorkflowDetail = {
  workflow: {
    workflow_id: '019e3ca1-3f22-7b90-bc34-9d5e2c7f1a44',
    name: 'run_agent',
    status: 'PENDING',
    created_at: 1779140000000,
    updated_at: 1779140000000,
    recovery_attempts: null,
    input: "{'args': ('DBOS vs Temporal performance benchmarks',), 'kwargs': {}}",
  },
  steps: [
    {
      function_id: 1,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'function_call',
            arguments: '{"query":"DBOS vs Temporal performance latency throughput benchmark"}',
            call_id: 'call_Pa1a',
            name: 'search_web',
            id: 'fc_p01',
            status: 'completed',
          },
        ],
        usage: { requests: 1, input_tokens: 162, output_tokens: 28, total_tokens: 190 },
        response_id: 'resp_pending_001',
        request_id: 'req_pending_001',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779140000120,
      completed_at_epoch_ms: 1779140002540,
    },
    {
      function_id: 2,
      function_name: 'search_web',
      output:
        'Title: DBOS Performance Benchmarks - Official Docs\nURL: https://docs.dbos.dev/benchmarks\nSummary: DBOS achieves sub-millisecond step overhead by using a single Postgres connection pool shared with your application, avoiding the network hops of external orchestrators.\n---\nTitle: Temporal Workflow Performance Guide\nURL: https://docs.temporal.io/concepts/what-is-a-worker#performance\nSummary: Temporal workers poll a server for tasks; network latency between worker and server is the primary performance variable in most deployments.',
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779140002545,
      completed_at_epoch_ms: 1779140005780,
    },
    {
      function_id: 3,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'function_call',
            arguments: '{"query":"DBOS Postgres durable execution overhead comparison self-hosted orchestration"}',
            call_id: 'call_Pa2b',
            name: 'search_web',
            id: 'fc_p02',
            status: 'completed',
          },
        ],
        usage: { requests: 1, input_tokens: 510, output_tokens: 36, total_tokens: 546 },
        response_id: 'resp_pending_002',
        request_id: 'req_pending_002',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779140005785,
      completed_at_epoch_ms: 1779140008310,
    },
    {
      function_id: 4,
      function_name: 'search_web',
      // In-flight: step started but output not yet stored
      output: null,
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779140008315,
      completed_at_epoch_ms: null,
    },
  ],
}

// ── ERROR fixture — step 5 fails, workflow aborts ─────────────────────────────

export const mockWorkflowError: WorkflowDetail = {
  workflow: {
    workflow_id: '019e3cb3-9a14-7c65-dd21-3b8f4e0d2c55',
    name: 'run_agent',
    status: 'ERROR',
    created_at: 1779138000000,
    updated_at: 1779138019420,
    recovery_attempts: 3,
    input: "{'args': ('quantum computing applications 2026',), 'kwargs': {}}",
  },
  steps: [
    {
      function_id: 1,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'function_call',
            arguments: '{"query":"quantum computing practical applications 2026"}',
            call_id: 'call_Er1a',
            name: 'search_web',
            id: 'fc_e01',
            status: 'completed',
          },
        ],
        usage: { requests: 1, input_tokens: 158, output_tokens: 29, total_tokens: 187 },
        response_id: 'resp_error_001',
        request_id: 'req_error_001',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779138000120,
      completed_at_epoch_ms: 1779138002610,
    },
    {
      function_id: 2,
      function_name: 'search_web',
      output:
        'Title: Quantum Computing in 2026: Where Are We Now?\nURL: https://spectrum.ieee.org/quantum-computing-2026\nSummary: Error correction has matured enough that small-scale fault-tolerant demonstrations are now routine, but practical quantum advantage over classical computers remains limited to narrow problem domains.\n---\nTitle: Top Quantum Computing Use Cases - McKinsey\nURL: https://www.mckinsey.com/quantum-computing-use-cases\nSummary: Drug discovery, materials simulation, and cryptography remain the leading use cases where quantum computing is expected to deliver meaningful speedups over classical approaches.',
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779138002615,
      completed_at_epoch_ms: 1779138005940,
    },
    {
      function_id: 3,
      function_name: '_model_call_step',
      output: {
        model: 'gpt-5.4-mini-2026-03-17',
        output: [
          {
            type: 'function_call',
            arguments: '{"query":"quantum advantage drug discovery materials science recent results"}',
            call_id: 'call_Er2b',
            name: 'search_web',
            id: 'fc_e02',
            status: 'completed',
          },
        ],
        usage: { requests: 1, input_tokens: 502, output_tokens: 38, total_tokens: 540 },
        response_id: 'resp_error_002',
        request_id: 'req_error_002',
      },
      error: null,
      child_workflow_id: null,
      started_at_epoch_ms: 1779138005945,
      completed_at_epoch_ms: 1779138008690,
    },
    {
      function_id: 4,
      function_name: 'search_web',
      output: null,
      error:
        "DDGSException: https://duckduckgo.com 429 Ratelimited. 429 Client Error: Too Many Requests for url: https://links.duckduckgo.com/d.js?...\nPlease try again later or reduce request frequency.",
      child_workflow_id: null,
      started_at_epoch_ms: 1779138008695,
      completed_at_epoch_ms: 1779138019415,
    },
  ],
}

// ── Workflow list — 10 entries ─────────────────────────────────────────────────
// Sorted newest-first. Three entries map to the detail fixtures above;
// the other seven are list-only (detail page shows an empty state for them).

export const mockWorkflowList: WorkflowSummary[] = [
  // PENDING / recovered once — just started
  {
    workflow_id: '019e3d70-6666-7abc-def0-667778901abc',
    name: 'run_agent',
    status: 'PENDING',
    created_at: 1779289080000,
    updated_at: 1779289085000,
    recovery_attempts: 1,
    step_count: 3,
    input: "{'args': ('Rust async runtime comparison',), 'kwargs': {}}",
  },
  // SUCCESS / no recovery — 30 min ago
  {
    workflow_id: '019e3d40-3333-7abc-def0-334456789abc',
    name: 'run_agent',
    status: 'SUCCESS',
    created_at: 1779287400000,
    updated_at: 1779287418000,
    recovery_attempts: 0,
    step_count: 6,
    input: "{'args': ('RAG architecture best practices',), 'kwargs': {}}",
  },
  // ERROR / no recovery — 1h ago
  {
    workflow_id: '019e3d80-7777-7abc-def0-778889012abc',
    name: 'run_agent',
    status: 'ERROR',
    created_at: 1779285600000,
    updated_at: 1779285618000,
    recovery_attempts: 0,
    step_count: 3,
    input: "{'args': ('neural network pruning techniques',), 'kwargs': {}}",
  },
  // SUCCESS / recovered once — 3h ago
  {
    workflow_id: '019e3d60-5555-7abc-def0-556667890abc',
    name: 'run_agent',
    status: 'SUCCESS',
    created_at: 1779278400000,
    updated_at: 1779278427000,
    recovery_attempts: 1,
    step_count: 7,
    input: "{'args': ('microservices vs monolith 2026',), 'kwargs': {}}",
  },
  // SUCCESS / no recovery — 5h ago
  {
    workflow_id: '019e3d20-1111-7abc-def0-123456789abc',
    name: 'run_agent',
    status: 'SUCCESS',
    created_at: 1779271200000,
    updated_at: 1779271221000,
    recovery_attempts: null,
    step_count: 9,
    input: "{'args': ('vector database comparison 2026',), 'kwargs': {}}",
  },
  // SUCCESS / no recovery — 8h ago
  {
    workflow_id: '019e3d30-2222-7abc-def0-223456789abc',
    name: 'run_agent',
    status: 'SUCCESS',
    created_at: 1779260400000,
    updated_at: 1779260420000,
    recovery_attempts: null,
    step_count: 5,
    input: "{'args': ('LLM fine-tuning techniques',), 'kwargs': {}}",
  },
  // SUCCESS / no recovery — yesterday (maps to mockWorkflowSuccess)
  {
    workflow_id: '019e3c95-08de-7451-af78-01a1f83c43bb',
    name: 'run_agent',
    status: 'SUCCESS',
    created_at: 1779132860641,
    updated_at: 1779132887183,
    recovery_attempts: null,
    step_count: 7,
    input: "{'args': ('durable execution',), 'kwargs': {}}",
  },
  // ERROR / 3 recoveries — yesterday (maps to mockWorkflowError)
  {
    workflow_id: '019e3cb3-9a14-7c65-dd21-3b8f4e0d2c55',
    name: 'run_agent',
    status: 'ERROR',
    created_at: 1779138000000,
    updated_at: 1779138019420,
    recovery_attempts: 3,
    step_count: 4,
    input: "{'args': ('quantum computing applications 2026',), 'kwargs': {}}",
  },
  // PENDING / no recovery — yesterday (maps to mockWorkflowPending)
  {
    workflow_id: '019e3ca1-3f22-7b90-bc34-9d5e2c7f1a44',
    name: 'run_agent',
    status: 'PENDING',
    created_at: 1779140000000,
    updated_at: 1779140008315,
    recovery_attempts: null,
    step_count: 4,
    input: "{'args': ('DBOS vs Temporal performance benchmarks',), 'kwargs': {}}",
  },
  // SUCCESS / recovered twice — 2 days ago
  {
    workflow_id: '019e3d50-4444-7abc-def0-445556789abc',
    name: 'run_agent',
    status: 'SUCCESS',
    created_at: 1779116400000,
    updated_at: 1779116437000,
    recovery_attempts: 2,
    step_count: 8,
    input: "{'args': ('transformer architecture explained',), 'kwargs': {}}",
  },
]
