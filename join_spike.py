#!/usr/bin/env python3
"""
Diagnostic: JOIN Phoenix span data with DBOS operation_outputs for one workflow run.
Feel the complexity of JOIN-in-app-code. Not production code.
"""
import json
import sqlite3
import textwrap
import time
import urllib.parse
import urllib.request

WORKFLOW_UUID = "019e27f7-5509-75d3-876c-891ec88c758c"
DB_PATH = "research_assistant.sqlite"
PHOENIX_BASE = "http://localhost:6006"
PROJECT = "default"


def phoenix_get(path: str) -> dict:
    t0 = time.monotonic()
    with urllib.request.urlopen(f"{PHOENIX_BASE}{path}") as r:
        data = json.loads(r.read())
    ms = (time.monotonic() - t0) * 1000
    print(f"  [phoenix] GET {path[:70]} → {ms:.0f}ms")
    return data


# ── 1. DBOS: pull workflow_status + operation_outputs ─────────────────────────
print("\n[1] Querying DBOS SQLite...")
con = sqlite3.connect(DB_PATH)
cur = con.cursor()

cur.execute(
    "SELECT * FROM workflow_status WHERE workflow_uuid = ?", (WORKFLOW_UUID,)
)
wf = dict(zip([d[0] for d in cur.description], cur.fetchone()))

cur.execute(
    "SELECT * FROM operation_outputs WHERE workflow_uuid = ? ORDER BY function_id",
    (WORKFLOW_UUID,),
)
ops = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
con.close()
print(f"  workflow={wf['name']} status={wf['status']} steps={len(ops)}")

# ── 2. Phoenix: find trace_id via operationUUID attribute filter ───────────────
print("\n[2] Querying Phoenix...")
attr = urllib.parse.quote(f"operationUUID:{WORKFLOW_UUID}")
dbos_resp = phoenix_get(f"/v1/projects/{PROJECT}/spans?attribute={attr}&limit=50")

trace_id = None
for s in dbos_resp["data"]:
    if s["name"] == wf["name"]:          # "run_agent" workflow root span
        trace_id = s["context"]["trace_id"]
        break

if not trace_id:
    raise RuntimeError("run_agent span not found — check operationUUID filter")

# Pull every span in the trace (DBOS + OpenInference, all in one call)
all_resp = phoenix_get(
    f"/v1/projects/{PROJECT}/spans?trace_id={trace_id}&limit=200"
)
all_spans = all_resp["data"]
print(f"  trace_id={trace_id}")
print(f"  total spans in trace: {len(all_spans)}")

# ── 3. Build span index and children map ──────────────────────────────────────
print("\n[3] Building span tree...")
by_id: dict[str, dict] = {s["context"]["span_id"]: s for s in all_spans}
children: dict[str | None, list[dict]] = {}
for s in all_spans:
    children.setdefault(s.get("parent_id"), []).append(s)

# ── 4. Index DBOS step spans by dbos.step_id attribute (keyed JOIN) ───────────
# Each step span now carries dbos.step_id = operation_outputs.function_id,
# so we can look up spans by key instead of relying on positional ordering.
step_spans_by_id: dict[int, dict] = {
    int(s["attributes"]["dbos.step_id"]): s
    for s in all_spans
    if s["span_kind"] == "UNKNOWN"
    and s["name"] != wf["name"]
    and "dbos.step_id" in s.get("attributes", {})
}
print(f"  step spans indexed by dbos.step_id: {sorted(step_spans_by_id.keys())}")

# ── 5. JOIN: per operation_outputs row, key-match on function_id == dbos.step_id
print("\n[5] Building unified records (keyed JOIN)...")
records = []

for i, op in enumerate(ops):
    step_span = step_spans_by_id.get(op["function_id"])
    if step_span is None:
        records.append({"turn_index": i + 1, "function_name": op["function_name"],
                         "status": "ERROR", "duration_ms": None,
                         "llm_model": None, "tokens_in": None, "tokens_out": None,
                         "tool_name": None, "tool_args": "NO SPAN FOUND"})
        continue

    # step_span.parent = TOOL span (OpenInference instruments @function_tool)
    tool_span = by_id.get(step_span.get("parent_id"))

    # TOOL span's parent = "turn" CHAIN span
    # LLM "response" span is a sibling of the TOOL span inside the same turn
    llm_span = None
    if tool_span:
        turn_id = tool_span.get("parent_id")
        siblings = children.get(turn_id, [])
        llm_span = next((s for s in siblings if s["span_kind"] == "LLM"), None)

    # Duration from DBOS durable timestamps (ms precision, exact)
    duration_ms: int | None = None
    if op["started_at_epoch_ms"] and op["completed_at_epoch_ms"]:
        duration_ms = op["completed_at_epoch_ms"] - op["started_at_epoch_ms"]

    tool_attrs = tool_span["attributes"] if tool_span else {}
    llm_attrs = llm_span["attributes"] if llm_span else {}

    # tool args are JSON-encoded in input.value
    raw_args = tool_attrs.get("input.value", "")
    try:
        parsed = json.loads(raw_args)
        short_args = textwrap.shorten(json.dumps(parsed), width=55)
    except (json.JSONDecodeError, TypeError):
        short_args = textwrap.shorten(str(raw_args), width=55)

    records.append(
        {
            "turn_index":    op["function_id"],
            "function_name": op["function_name"],
            "status":        "SUCCESS" if op["error"] is None else "ERROR",
            "duration_ms":   duration_ms,
            "llm_model":     llm_attrs.get("llm.model_name"),
            "tokens_in":     llm_attrs.get("llm.token_count.prompt"),
            "tokens_out":    llm_attrs.get("llm.token_count.completion"),
            "tool_name":     tool_attrs.get("tool.name"),
            "tool_args":     short_args,
        }
    )

# ── 6. Print ──────────────────────────────────────────────────────────────────
print(f"\n{'─'*100}")
print(f"Workflow: {WORKFLOW_UUID}")
print(f"  name={wf['name']}  status={wf['status']}")
print(f"{'─'*100}")

hdr = (
    f"{'#':>2}  {'function':12}  {'status':8}  {'ms':>6}  "
    f"{'model':30}  {'in':>5}  {'out':>4}  {'tool':12}  args"
)
print(hdr)
print("-" * len(hdr))

for r in records:
    print(
        f"{r['turn_index']:>2}  "
        f"{r['function_name']:12}  "
        f"{r['status']:8}  "
        f"{str(r['duration_ms'] if r['duration_ms'] is not None else '?'):>6}  "
        f"{str(r['llm_model'] or '?'):30}  "
        f"{str(r['tokens_in'] or '?'):>5}  "
        f"{str(r['tokens_out'] or '?'):>4}  "
        f"{str(r['tool_name'] or '?'):12}  "
        f"{r['tool_args']}"
    )
