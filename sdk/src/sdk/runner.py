import dataclasses
from typing import Any
from agents import Agent, Runner, RunConfig, RunResult
from agents.items import ModelResponse
from agents.models.multi_provider import MultiProvider
from dbos import DBOS
from dbos_openai_agents.runner import DBOSModelWrapper, DBOSModelProvider, _State, _wrap_agent


class OurModelWrapper(DBOSModelWrapper):
    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        print("OurModelWrapper.get_response called")
        result = await super().get_response(*args, **kwargs)
        await _extract_and_store(result)
        return result


class OurModelProvider(DBOSModelProvider):
    def __init__(self, state: _State):
        super().__init__(state)
        self._state = state

    def get_model(self, model_name: str | None):
        base_model = MultiProvider.get_model(self, model_name or None)
        return OurModelWrapper(base_model, self._state)


class OurRunner:
    @classmethod
    async def run(cls, agent: Agent, input: str, **kwargs: Any) -> RunResult:
        state = _State()
        run_config = kwargs.pop("run_config", RunConfig())
        run_config = dataclasses.replace(
            run_config,
            model_provider=OurModelProvider(state),
        )
        wrapped_agent = _wrap_agent(agent, state)
        return await Runner.run(
            starting_agent=wrapped_agent,
            input=input,
            run_config=run_config,
            **kwargs,
        )


async def _extract_and_store(result: ModelResponse) -> None:
    workflow_id = DBOS.workflow_id

    has_tool_calls = any(
        item.type == "function_call" for item in result.output
    )
    kind = "tool_call_decision" if has_tool_calls else "final_answer"

    input_tokens = result.usage.input_tokens
    output_tokens = result.usage.output_tokens
    total_tokens = result.usage.total_tokens

    tools = [
        {"name": item.name, "arguments": item.arguments}
        for item in result.output
        if item.type == "function_call"
    ]

    print(f"\n{'─' * 50}")
    print(f"  workflow_id:  {workflow_id}")
    print(f"  kind:         {kind}")
    print(f"  tokens:       {input_tokens} in / {output_tokens} out / {total_tokens} total")
    if tools:
        print(f"  tool calls:   {len(tools)}")
        for t in tools:
            print(f"    → {t['name']}: {t['arguments']}")
    print(f"{'─' * 50}")
