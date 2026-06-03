import sys
import types
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def clear_amber_modules():
    for module_name in ("amber.runtime", "amber.decorators", "amber"):
        sys.modules.pop(module_name, None)


def install_agents_stubs():
    agents = types.ModuleType("agents")
    ddgs = types.ModuleType("ddgs")

    class Agent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.name = kwargs.get("name")
            self.tools = kwargs.get("tools", [])
            self.handoffs = kwargs.get("handoffs", [])

    def function_tool(fn=None, **_kwargs):
        def decorator(target):
            target._is_function_tool = True
            return target

        if fn is None:
            return decorator
        return decorator(fn)

    class DDGS:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def text(self, *_args, **_kwargs):
            return []

    agents.Agent = Agent
    agents.function_tool = function_tool
    ddgs.DDGS = DDGS

    sys.modules["agents"] = agents
    sys.modules["ddgs"] = ddgs


def install_amber_stub():
    registered_agents = {}
    amber = types.ModuleType("amber")

    def register_agent(*, name, max_recovery_attempts=5):
        def decorator(fn):
            fn._dbos_workflow_name = name
            fn._dbos_max_recovery_attempts = max_recovery_attempts
            registered_agents[name] = types.SimpleNamespace(name=name, workflow=fn)
            return fn

        return decorator

    def list_registered_agents():
        return [registered_agents[name] for name in sorted(registered_agents)]

    def step(**_kwargs):
        def decorator(fn):
            return fn

        return decorator

    async def sleep(_seconds):
        return None

    async def agent_runner(**_kwargs):
        raise AssertionError("agent_runner should be patched by the test")

    class DBOSContext:
        workflow_id = "workflow-1"

    amber.register_agent = register_agent
    amber.list_registered_agents = list_registered_agents
    amber.agent_runner = agent_runner
    amber.current_workflow_id = lambda: DBOSContext.workflow_id
    amber.logger = mock.Mock()
    amber.sleep = sleep
    amber.step = step
    sys.modules["amber"] = amber
    return amber, DBOSContext
