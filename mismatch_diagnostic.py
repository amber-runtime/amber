#!/usr/bin/env python3
"""
Diagnostic: visualise the step-level key mismatch between DBOS and Phoenix.
Shows what each side knows and what key they share (and don't).
"""
import json
import sqlite3
import urllib.parse
import urllib.request

WORKFLOW_UUID = "019e2786-b1ee-707a-a6ad-97f477e5b654"
DB_PATH = "research_assistant.sqlite"
PHOENIX_BASE = "http://localhost:6006"
PROJECT = "default"


def phoenix_get(path: str) -> dict:
    with urllib.request.urlopen(f"{PHOENIX_BASE}{path}") as r:
        return json.loads(r.read())


# ── DBOS ──────────────────────────────────────────────────────────────────────
con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.execute(
    "SELECT function_id, function_name, started_at_epoch_ms"
    " FROM operation_outputs WHERE workflow_uuid = ? ORDER BY function_id",
    (WORKFLOW_UUID,),
)
dbos_steps = cur.fetchall()
con.close()

# ── Phoenix ───────────────────────────────────────────────────────────────────
attr = urllib.parse.quote(f"operationUUID:{WORKFLOW_UUID}")
resp = phoenix_get(f"/v1/projects/{PROJECT}/spans?attribute={attr}&limit=50")

# DBOS step spans: UNKNOWN kind, not the workflow root
step_spans = sorted(
    [s for s in resp["data"] if s["span_kind"] == "UNKNOWN" and s["name"] != "run_agent"],
    key=lambda s: s["start_time"],
)

# Convert ISO start_time to epoch-ms for display parity with DBOS
def iso_to_ms(iso: str) -> int:
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)

phoenix_rows = [
    (
        s["context"]["span_id"][:8],
        s["name"],
        iso_to_ms(s["start_time"]),
    )
    for s in step_spans
]

# ── Side-by-side printout ─────────────────────────────────────────────────────
L_W = 52  # left column width

left_hdr  = f"{'DBOS operation_outputs':^{L_W}}"
right_hdr = f"{'Phoenix DBOS step spans':^{L_W}}"
print(f"\n{left_hdr}  {right_hdr}")
print(f"{'─' * L_W}  {'─' * L_W}")

left_col_hdr  = f"{'function_id':>11}  {'function_name':14}  {'started_at_ms':>13}"
right_col_hdr = f"{'span_id[:8]':>10}  {'name':14}  {'start_time_ms':>13}"
print(f"{left_col_hdr}  {right_col_hdr}")
print(f"{'─' * L_W}  {'─' * L_W}")

rows = max(len(dbos_steps), len(phoenix_rows))
for i in range(rows):
    if i < len(dbos_steps):
        fid, fname, ts = dbos_steps[i]
        left = f"{fid:>11}  {fname:14}  {ts:>13}"
    else:
        left = " " * L_W

    if i < len(phoenix_rows):
        sid, sname, ts = phoenix_rows[i]
        right = f"{sid:>10}  {sname:14}  {ts:>13}"
    else:
        right = ""

    print(f"{left}  {right}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'─' * 106}")
print("Key mismatch summary")
print(f"{'─' * 106}")
print("  Shared keys at step level : NONE")
print(f"  Only in DBOS              : function_id  (e.g. {dbos_steps[0][0] if dbos_steps else '?'})")
print(f"  Only in Phoenix           : span_id      (e.g. {phoenix_rows[0][0] + '...' if phoenix_rows else '?'})")
print()
print("  Workflow-level overlap:")
print(f"    DBOS    workflow_uuid     = {WORKFLOW_UUID}")
op_uuid = resp["data"][0]["attributes"].get("operationUUID", "?") if resp["data"] else "?"
print(f"    Phoenix operationUUID     = {op_uuid}")
print(f"    Match: {WORKFLOW_UUID == op_uuid}")
