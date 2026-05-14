# quick start
#   cd backend_api
#   uv run uvicorn main:app --port 8001 --reload

# backend API:
#  GET workflows
#   -> returns JSON list of workflows
#  POST workflows/:id/resume
#   -> calls DBOS app's resume endpoint
#     **caveat: DBOS app that initiated that workflow must be actively running
#     on separate server. (DBOS app must be running on DBOS_APP_URL)
import os
from datetime import datetime, timezone

import httpx
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()

app = FastAPI()

DATABASE_URL = os.environ["DATABASE_URL"]
DBOS_APP_URL = os.environ["DBOS_APP_URL"]


def get_connection():
    return psycopg.connect(DATABASE_URL)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/workflows/{workflow_id}/resume")
def resume_workflow(workflow_id: str):
    print(f"workflow resume request for workflow_id: {workflow_id}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM dbos.workflow_status WHERE workflow_uuid = %s",
                (workflow_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if row[0] == "SUCCESS":
        raise HTTPException(
            status_code=400,
            detail="Cannot resume a workflow that has already succeeded",
        )

    httpx.post(f"{DBOS_APP_URL}/resume/{workflow_id}", timeout=None)
    return {"workflow_id": workflow_id, "status": "queued"}


@app.get("/workflows")
def list_workflows():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT workflow_uuid, status, name, created_at, error
                FROM dbos.workflow_status
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()

    return [
        {
            "workflow_id": row[0],
            "status": row[1],
            "name": row[2],
            "created_at": datetime.fromtimestamp(row[3] / 1000, tz=timezone.utc).isoformat(),
            "error": row[4],
        }
        for row in rows
    ]
