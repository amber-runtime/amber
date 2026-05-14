# Note
- actually to simplify, we should just mount these routes to the active DBOS app instead of running these routes on a seperate server

# quick start
  cd backend_api
  uv run uvicorn main:app --port 8001 --reload

# backend API:
 GET workflows
  -> returns JSON list of workflows
 POST workflows/:id/resume
  -> calls DBOS app's resume endpoint
    **caveat: DBOS app that initiated that workflow must be actively running
    on separate server. (DBOS app must be running on DBOS_APP_URL)

# IMPORTANT
- to use resume endpoint, your dbos app must expose this route
```
@app.post("/resume/{workflow_id}")
def resume(workflow_id: str):
    DBOS.resume_workflow(workflow_id)
    return {"status": "queued"}
```