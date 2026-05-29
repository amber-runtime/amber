# Example Customer App

## Error Demo

Use `account-research-error-demo` to show durable debugging with forked workflows.

Story:
- the workflow runs several research subagents
- it sends the AE brief email as an irreversible side effect
- for enterprise accounts it enters a rare deep-scan branch
- that deep scan fails with a generic `ConnectionError`

In the launcher UI, enable `Fail deep scan on rate limit` to force the failure path.

## Demo Flow

1. Naive run: the email sends, then the deep scan fails.
2. Fork 1: uncomment the `DEMO FORK 1` line in [user_agents/account_research_error_demo.py](/Users/Danny/repos/playground/example_customer_app/user_agents/account_research_error_demo.py:311) to log the real throttle cause.
3. Fork 2: uncomment the `DEMO FORK 2` line in [user_agents/account_research_error_demo.py](/Users/Danny/repos/playground/example_customer_app/user_agents/account_research_error_demo.py:306) to add backoff so the forked run succeeds.

Notes:
- restart the worker after changing a lever
- earlier research steps and the email send should not replay on forks
