"""
Queue worker for the customer app demo.

Run:
  uv run python -m example_customer_app.worker
"""

from dotenv import load_dotenv

from sdk import run_agent_worker

load_dotenv()


def main() -> None:
    run_agent_worker(
        agent_modules=[
            "example_customer_app.user_agents.single_agent_demo",
            "example_customer_app.user_agents.multi_agent_demo",
            "example_customer_app.user_agents.queued_multi_agent_demo",
        ],
        queue_name="agent-runs",
        worker_concurrency=1,
    )


if __name__ == "__main__":
    main()
