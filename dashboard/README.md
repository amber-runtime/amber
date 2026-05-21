# Amber Dashboard

Frontend for visualizing Amber workflow runs. Renders the step timeline, tool calls, and final answer for each run.

## Status

v1, internal tool. Currently runs on mock fixtures. Backend wiring is the next milestone.

## Setup

Requires Node.js 18+.

```bash
cd dashboard
npm install
npm run dev
```

Opens at `http://localhost:5173`.

## Stack

Vite + React 19 + TypeScript + Tailwind. Uses `react-markdown` for final answer rendering and `lucide-react` for icons.

## Mock data

Three fixtures are baked in: SUCCESS, PENDING, ERROR. Swap between them via the "Fixture" dropdown in the corner.

## What's not yet implemented

- Backend wiring (all data is mock right now)
- Workflow list view (workflow ID is hardcoded)
- Real-time updates for in-progress workflows
- Crash-recovery visualization
- Workflow actions (cancel, resume, fork)

## Backend prerequisites (for future wiring)

Targets `single_server_poc.py` on port 8002. Pending one-line backend changes before wiring:codex

- `load_output=True` so the final answer card renders
- `load_input=True` so the topic card renders
- `recovery_attempts` actually populated (currently hardcoded `null`)
