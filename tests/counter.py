import os
from sdk import workflow, step, sleep, init
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI

load_dotenv(find_dotenv())
app = FastAPI()
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

@step()
def step_one():
    print("Step one completed!")

@step()
def step_two():
    print("Step two completed!")

@workflow(max_recovery_attempts=0)
def dbos_workflow():
    step_one()
    for _ in range(10):
        print("Press Control + C (or Control + \) to stop the app...")
        sleep(1)
    step_two()

# if __name__ == "__main__":
#     init(name="counter")
#     dbos_workflow()

@app.on_event("startup")
async def startup() -> None:
    init(
        name="agent-demo",
        db_url=os.environ["DBOS_SYSTEM_DATABASE_URL"],
        conductor_key=os.environ["DBOS_CONDUCTOR_KEY"]
        )

@app.post("/run")
async def workflow():
    return dbos_workflow()