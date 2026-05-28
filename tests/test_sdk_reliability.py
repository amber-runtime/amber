import ast
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def iso_utc_from_ms(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


queries = load_module("queries_under_test", "sdk/src/sdk/dashboard/queries.py")


class QueryTests(unittest.IsolatedAsyncioTestCase):
    def test_build_step_records_marks_ambiguous_null_step_tools(self):
        steps = [
            {"function_id": 1, "function_name": "lookup", "error": None},
            {"function_id": 2, "function_name": "lookup", "error": None},
        ]
        events = [
            {
                "span_id": "span-1",
                "step_id": None,
                "event_type": "tool_call",
                "tool_name": "lookup",
                "tool_args": {"q": "a"},
            },
            {
                "span_id": "span-2",
                "step_id": None,
                "event_type": "tool_call",
                "tool_name": "lookup",
                "tool_args": {"q": "b"},
            },
        ]

        records = queries.build_step_records(steps, events)

        self.assertEqual(records[0]["tool_name"], "lookup")
        self.assertIsNone(records[0]["tool_args"])
        self.assertEqual(records[0]["event_type"], "step")
        self.assertEqual(records[1]["event_type"], "step")

    def test_build_step_records_attaches_single_unambiguous_null_step_tool(self):
        steps = [{"function_id": 1, "function_name": "lookup", "error": None}]
        events = [
            {
                "span_id": "span-1",
                "step_id": None,
                "event_type": "tool_call",
                "tool_name": "lookup",
                "tool_args": {"q": "a"},
            }
        ]

        records = queries.build_step_records(steps, events)

        self.assertEqual(records[0]["tool_args"], {"q": "a"})
        self.assertEqual(records[0]["event_type"], "tool_call")

    def test_build_step_records_tolerates_missing_dbos_keys(self):
        records = queries.build_step_records([{"error": None}], [])

        self.assertEqual(records[0]["status"], "SUCCESS")
        self.assertIsNone(records[0]["step_id"])
        self.assertIsNone(records[0]["function_name"])
        self.assertEqual(records[0]["event_type"], "step")
        self.assertIsNone(records[0]["step_output"])

    def test_build_step_records_carries_dbos_native_output_for_plain_steps(self):
        steps = [
            {
                "function_id": 1,
                "function_name": "normalize_travel_request",
                "output": {"destination": "Tokyo", "guests": 2},
                "error": None,
                "child_workflow_id": None,
                "started_at_epoch_ms": 1_747_830_400_000,
                "completed_at_epoch_ms": 1_747_830_405_250,
            }
        ]

        records = queries.build_step_records(steps, [])

        self.assertEqual(records[0]["event_type"], "step")
        self.assertEqual(
            records[0]["step_output"],
            {"destination": "Tokyo", "guests": 2},
        )

    def test_build_step_records_falls_back_to_completed_at_for_plain_steps(self):
        steps = [
            {
                "function_id": 1,
                "function_name": "normalize_travel_request",
                "output": {"destination": "Tokyo", "guests": 2},
                "error": None,
                "started_at_epoch_ms": 1_747_830_400_000,
                "completed_at_epoch_ms": 1_747_830_405_250,
            }
        ]

        records = queries.build_step_records(steps, [])

        self.assertEqual(records[0]["duration_ms"], 5250)
        self.assertEqual(
            records[0]["captured_at"],
            iso_utc_from_ms(1_747_830_405_250),
        )

    def test_build_step_records_falls_back_to_started_at_for_in_progress_plain_steps(self):
        steps = [
            {
                "function_id": 3,
                "function_name": "lookup_price",
                "output": None,
                "error": None,
                "started_at_epoch_ms": 1_747_830_410_000,
                "completed_at_epoch_ms": None,
            }
        ]

        records = queries.build_step_records(steps, [])

        self.assertIsNone(records[0]["duration_ms"])
        self.assertEqual(
            records[0]["captured_at"],
            iso_utc_from_ms(1_747_830_410_000),
        )

    def test_build_step_records_marks_dbos_native_errors(self):
        steps = [
            {
                "function_id": 2,
                "function_name": "lookup_price",
                "output": None,
                "error": ValueError("bad lookup"),
                "child_workflow_id": "wf-child-1",
            }
        ]

        records = queries.build_step_records(steps, [])

        self.assertEqual(records[0]["status"], "ERROR")

    def test_build_step_records_carries_llm_raw_io(self):
        steps = [{"function_id": 1, "function_name": "_model_call_step", "error": None}]
        events = [
            {
                "span_id": "span-1",
                "step_id": 1,
                "event_type": "llm_response",
                "model": "gpt-5.4-mini",
                "tokens_in": 10,
                "tokens_out": 5,
                "llm_input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
                "llm_output": [{"type": "message", "id": "msg_123"}],
                "captured_at": "2026-05-21T12:00:00Z",
            }
        ]

        records = queries.build_step_records(steps, events)

        self.assertEqual(records[0]["event_type"], "llm_response")
        self.assertEqual(records[0]["llm_input"], events[0]["llm_input"])
        self.assertEqual(records[0]["llm_output"], events[0]["llm_output"])
        self.assertEqual(records[0]["captured_at"], events[0]["captured_at"])

    def test_build_step_records_prefers_event_timestamp_over_dbos_timing(self):
        steps = [
            {
                "function_id": 1,
                "function_name": "_model_call_step",
                "error": None,
                "started_at_epoch_ms": 1_747_830_400_000,
                "completed_at_epoch_ms": 1_747_830_405_000,
            }
        ]
        events = [
            {
                "span_id": "span-1",
                "step_id": 1,
                "event_type": "llm_response",
                "captured_at": "2026-05-21T12:00:00Z",
            }
        ]

        records = queries.build_step_records(steps, events)

        self.assertEqual(records[0]["captured_at"], "2026-05-21T12:00:00Z")

    def test_build_step_records_carries_agent_name_for_llm_steps(self):
        steps = [{"function_id": 1, "function_name": "_model_call_step", "error": None}]
        events = [
            {
                "span_id": "span-1",
                "step_id": 1,
                "event_type": "llm_response",
                "agent_name": "flight_researcher",
            }
        ]

        records = queries.build_step_records(steps, events)

        self.assertEqual(records[0]["agent_name"], "flight_researcher")

    def test_build_step_records_carries_tool_result_and_timestamp_for_tool_steps(self):
        steps = [{"function_id": 6, "function_name": "get_flight_quotes", "error": None}]
        events = [
            {
                "span_id": "span-6",
                "step_id": 6,
                "event_type": "tool_call",
                "tool_name": "get_flight_quotes",
                "tool_args": {"origin": "SFO"},
                "tool_result": "best flight selected",
                "captured_at": "2026-05-21T12:00:01Z",
            }
        ]

        records = queries.build_step_records(steps, events)

        self.assertEqual(records[0]["event_type"], "tool_call")
        self.assertEqual(records[0]["tool_result"], "best flight selected")
        self.assertEqual(records[0]["captured_at"], "2026-05-21T12:00:01Z")

    def test_build_step_records_carries_agent_name_for_tool_steps(self):
        steps = [{"function_id": 6, "function_name": "get_flight_quotes", "error": None}]
        events = [
            {
                "span_id": "span-6",
                "step_id": 6,
                "event_type": "tool_call",
                "agent_name": "flight_researcher",
                "tool_name": "get_flight_quotes",
            }
        ]

        records = queries.build_step_records(steps, events)

        self.assertEqual(records[0]["event_type"], "tool_call")
        self.assertEqual(records[0]["agent_name"], "flight_researcher")

    async def test_fetch_agent_events_for_dashboard_swallows_read_failures(self):
        with (
            mock.patch.object(queries, "fetch_agent_events_async", side_effect=RuntimeError("boom")),
            self.assertLogs(queries.logger, level="ERROR"),
        ):
            events = await queries.fetch_agent_events_for_dashboard("wf", "postgresql://db")

        self.assertEqual(events, [])

    async def test_get_workflow_loads_output_for_dashboard_detail(self):
        dbos = types.ModuleType("dbos")

        class DBOS:
            @staticmethod
            async def list_workflows_async(**kwargs):
                self.assertTrue(kwargs["load_output"])
                self.assertFalse(kwargs["load_input"])
                return [
                    types.SimpleNamespace(
                        workflow_id="wf-1",
                        name="travel-concierge",
                        status="SUCCESS",
                        created_at=1,
                        updated_at=2,
                        output={"answer": "done"},
                    )
                ]

        dbos.DBOS = DBOS
        with mock.patch.dict(sys.modules, {"dbos": dbos}):
            workflow = await queries.get_workflow("wf-1")

        self.assertEqual(workflow["output"], "{'answer': 'done'}")


def install_tracing_stubs():
    agents = types.ModuleType("agents")
    tracing_pkg = types.ModuleType("agents.tracing")
    processor_interface = types.ModuleType("agents.tracing.processor_interface")
    span_data = types.ModuleType("agents.tracing.span_data")
    dbos = types.ModuleType("dbos")

    class TracingProcessor:
        pass

    class AgentSpanData:
        def __init__(self, name=None, handoffs=None, tools=None, output_type=None, metadata=None):
            self.name = name

    class TurnSpanData:
        def __init__(self, turn=None, agent_name=None, usage=None, metadata=None):
            self.turn = turn
            self.agent_name = agent_name

    class FunctionSpanData:
        def __init__(self, name=None, input=None, output=None):
            self.name = name
            self.input = input
            self.output = output

    class GenerationSpanData:
        def __init__(self, input=None, output=None, model=None, model_config=None, usage=None):
            self.input = input
            self.output = output
            self.model = model
            self.model_config = model_config
            self.usage = usage

    class HandoffSpanData:
        pass

    class ResponseSpanData:
        def __init__(self, response=None, input=None, usage=None):
            self.response = response
            self.input = input
            self.usage = usage

    class DBOS:
        workflow_id = "workflow-1"
        step_id = 7

    processor_interface.TracingProcessor = TracingProcessor
    span_data.AgentSpanData = AgentSpanData
    span_data.FunctionSpanData = FunctionSpanData
    span_data.GenerationSpanData = GenerationSpanData
    span_data.HandoffSpanData = HandoffSpanData
    span_data.ResponseSpanData = ResponseSpanData
    span_data.TurnSpanData = TurnSpanData
    dbos.DBOS = DBOS
    tracing_pkg.add_trace_processor = mock.Mock()

    sys.modules["agents"] = agents
    sys.modules["agents.tracing"] = tracing_pkg
    sys.modules["agents.tracing.processor_interface"] = processor_interface
    sys.modules["agents.tracing.span_data"] = span_data
    sys.modules["dbos"] = dbos

    return (
        AgentSpanData,
        TurnSpanData,
        FunctionSpanData,
        GenerationSpanData,
        ResponseSpanData,
        DBOS,
        tracing_pkg.add_trace_processor,
    )


def install_decorator_stubs():
    dbos = types.ModuleType("dbos")
    dbos_openai_agents = types.ModuleType("dbos_openai_agents")

    class DBOS:
        logger = mock.Mock()
        workflow_id = "workflow-1"
        init_calls = []
        launch = mock.Mock()
        call_order = []
        started_workflows = []
        enqueued_workflows = []
        listened_queues = []
        registered_queues = []

        def __init__(self, config=None):
            self.config = config
            DBOS.init_calls.append(config)
            DBOS.call_order.append("init")

        @staticmethod
        def workflow(name=None, max_recovery_attempts=None):
            def decorator(fn):
                fn._dbos_workflow_name = name
                fn._dbos_max_recovery_attempts = max_recovery_attempts
                return fn

            return decorator

        @staticmethod
        def step(**_kwargs):
            def decorator(fn):
                return fn

            return decorator

        @staticmethod
        async def start_workflow_async(workflow, input):
            DBOS.started_workflows.append((workflow, input))
            return types.SimpleNamespace(workflow_id="workflow-started")

        @staticmethod
        def register_queue(name, **kwargs):
            DBOS.registered_queues.append((name, kwargs))
            DBOS.call_order.append(("register_queue", name))
            return types.SimpleNamespace(name=name)

        @staticmethod
        def listen_queues(queues):
            DBOS.listened_queues.append(list(queues))
            DBOS.call_order.append(("listen_queues", list(queues)))

        @staticmethod
        async def enqueue_workflow_async(queue_name, workflow, input):
            DBOS.enqueued_workflows.append((queue_name, workflow, input))
            return types.SimpleNamespace(workflow_id="workflow-enqueued")

    class DBOSRunner:
        pass

    class DBOSClient:
        pass

    DBOS.launch = mock.Mock(side_effect=lambda: DBOS.call_order.append("launch"))

    dbos.DBOS = DBOS
    dbos.DBOSClient = DBOSClient
    dbos.DBOSConfig = dict
    dbos_openai_agents.DBOSRunner = DBOSRunner

    sys.modules["dbos"] = dbos
    sys.modules["dbos_openai_agents"] = dbos_openai_agents
    return DBOS


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


class AgentRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env_patcher = mock.patch.dict(
            os.environ, {"DB_URL": "postgres://db"}, clear=False
        )
        self.env_patcher.start()
        self.DBOS = install_decorator_stubs()
        self.env_patcher = mock.patch.dict(
            os.environ,
            {"DB_URL": "sqlite:///test"},
            clear=False,
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        sdk_src = ROOT / "sdk" / "src"
        if str(sdk_src) not in sys.path:
            sys.path.insert(0, str(sdk_src))
        sys.modules.pop("sdk", None)
        sys.modules.pop("sdk.runtime", None)
        sys.modules.pop("sdk.decorators", None)
        self.decorators = load_module("sdk.decorators", "sdk/src/sdk/decorators.py")
        sys.modules["sdk.decorators"] = self.decorators
        self.runtime = importlib.import_module("sdk.runtime")
        self.decorators = importlib.import_module("sdk.decorators")

    def tearDown(self):
        self.env_patcher.stop()

    def test_agent_decorator_registers_named_workflow(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="research-assistant")(run_topic)

        registered = self.decorators.get_registered_agent("research-assistant")
        self.assertEqual(registered.name, "research-assistant")
        self.assertIs(registered.workflow, workflow_fn)
        self.assertFalse(registered.queued)
        self.assertEqual(workflow_fn._dbos_workflow_name, "research-assistant")

    def test_agent_decorator_stores_queued_metadata(self):
        async def run_topic(topic: str) -> str:
            return topic

        self.decorators.register_agent(name="research-handoff-agent", queued=True)(run_topic)

        registered = self.decorators.get_registered_agent("research-handoff-agent")
        self.assertTrue(registered.queued)

    def test_agent_decorator_rejects_duplicate_names(self):
        self.decorators.register_agent(name="research-assistant")(lambda value: value)

        with self.assertRaisesRegex(ValueError, "already registered"):
            self.decorators.register_agent(name="research-assistant")(lambda value: value)

    def test_get_registered_agent_reports_available_names(self):
        self.decorators.register_agent(name="research-assistant")(lambda value: value)

        with self.assertRaisesRegex(ValueError, "research-assistant"):
            self.decorators.get_registered_agent("missing-agent")

    def test_list_registered_agents_is_sorted_by_name(self):
        self.decorators.register_agent(name="zeta")(lambda value: value)
        self.decorators.register_agent(name="alpha")(lambda value: value)

        self.assertEqual(
            [agent.name for agent in self.decorators.list_registered_agents()],
            ["alpha", "zeta"],
        )

    def test_runtime_start_is_idempotent_and_reads_embedded_env(self):
        with mock.patch.dict(
            os.environ,
            {
                "CHECKPOINT_RUNTIME_NAME": "embedded-app",
                "DB_URL": "postgres://primary",
                "DBOS_SYSTEM_DATABASE_URL": "postgresql://system",
                "CHECKPOINT_CONDUCTOR_KEY": "key-1",
            },
            clear=False,
        ):
            runtime = self.runtime.Runtime()
            runtime.start()
            runtime.start()

        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()
        self.assertEqual(self.DBOS.init_calls[0]["name"], "embedded-app")
        self.assertEqual(
            self.DBOS.init_calls[0]["system_database_url"],
            "postgres://primary",
        )
        self.assertEqual(self.DBOS.init_calls[0]["conductor_key"], "key-1")

    def test_runtime_start_can_disable_queue_listening_before_launch(self):
        runtime = self.runtime.Runtime()
        runtime.start(listen_queues=[])

        self.assertEqual(self.DBOS.listened_queues, [[]])
        self.assertEqual(
            self.DBOS.call_order,
            ["init", ("listen_queues", []), "launch"],
        )
        self.DBOS.launch.assert_called_once()

    def test_runtime_start_rejects_listener_changes_after_launch(self):
        runtime = self.runtime.Runtime()
        runtime.start()

        with self.assertRaisesRegex(RuntimeError, "before DBOS.launch"):
            runtime.start(listen_queues=[])

        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()

    async def test_agent_service_run_initializes_once_and_starts_registered_workflow(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="alpha")(run_topic)
        agents = self.runtime.AgentService()

        first = await agents.run("alpha", "hello")
        second = await agents.run("alpha", "again")

        self.assertEqual(first.workflow_id, "workflow-started")
        self.assertEqual(second.workflow_id, "workflow-started")
        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()
        self.assertEqual(
            self.DBOS.started_workflows,
            [(workflow_fn, "hello"), (workflow_fn, "again")],
        )

    async def test_agent_service_start_runs_immediate_registered_agent(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="alpha")(run_topic)
        agents = self.runtime.AgentService()

        handle = await agents.start("alpha", "hello")

        self.assertEqual(handle.workflow_id, "workflow-started")
        self.assertEqual(self.DBOS.started_workflows, [(workflow_fn, "hello")])
        self.assertEqual(self.DBOS.enqueued_workflows, [])
        self.assertEqual(self.DBOS.registered_queues, [])

    async def test_agent_service_start_enqueues_queued_registered_agent(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="alpha", queued=True)(run_topic)
        agents = self.runtime.AgentService()

        handle = await agents.start("alpha", "hello")

        self.assertEqual(handle.workflow_id, "workflow-enqueued")
        self.assertEqual(self.DBOS.started_workflows, [])
        self.assertEqual(
            self.DBOS.registered_queues,
            [("agent-runs", {"on_conflict": "never_update"})],
        )
        self.assertEqual(
            self.DBOS.enqueued_workflows,
            [("agent-runs", workflow_fn, "hello")],
        )

    async def test_agent_service_start_queue_name_override_applies_to_queued_agents_only(self):
        async def run_topic(topic: str) -> str:
            return topic

        queued_workflow = self.decorators.register_agent(name="queued", queued=True)(run_topic)
        immediate_workflow = self.decorators.register_agent(name="immediate")(run_topic)
        agents = self.runtime.AgentService()

        queued_handle = await agents.start("queued", "queued-input", queue_name="slow-lane")
        immediate_handle = await agents.start("immediate", "immediate-input", queue_name="slow-lane")

        self.assertEqual(queued_handle.workflow_id, "workflow-enqueued")
        self.assertEqual(immediate_handle.workflow_id, "workflow-started")
        self.assertEqual(
            self.DBOS.registered_queues,
            [("slow-lane", {"on_conflict": "never_update"})],
        )
        self.assertEqual(
            self.DBOS.enqueued_workflows,
            [("slow-lane", queued_workflow, "queued-input")],
        )
        self.assertEqual(
            self.DBOS.started_workflows,
            [(immediate_workflow, "immediate-input")],
        )

    def test_worker_service_register_queue_initializes_and_registers_queue(self):
        worker = self.runtime.WorkerService(
            agent_modules=["customer_agent_module"],
            queue_name="agent-runs",
            worker_concurrency=2,
            concurrency=5,
            keep_alive=False,
        )

        worker.register_queue()

        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()
        self.assertEqual(
            self.DBOS.registered_queues,
            [
                (
                    "agent-runs",
                    {
                        "worker_concurrency": 2,
                        "concurrency": 5,
                        "limiter": None,
                        "priority_enabled": False,
                        "partition_queue": False,
                        "polling_interval_sec": 1.0,
                        "on_conflict": "update_if_latest_version",
                    },
                )
            ],
        )

    def test_worker_service_accepts_global_concurrency_equal_to_worker_concurrency(self):
        worker = self.runtime.WorkerService(
            agent_modules=["customer_agent_module"],
            queue_name="agent-runs",
            worker_concurrency=4,
            concurrency=4,
            keep_alive=False,
        )

        self.assertEqual(worker.worker_concurrency, 4)
        self.assertEqual(worker.concurrency, 4)

    def test_worker_service_rejects_global_concurrency_below_worker_concurrency(self):
        with self.assertRaisesRegex(
            ValueError,
            "concurrency must be greater than or equal to worker_concurrency",
        ):
            self.runtime.WorkerService(
                agent_modules=["customer_agent_module"],
                queue_name="agent-runs",
                worker_concurrency=5,
                concurrency=4,
                keep_alive=False,
            )

    async def test_agent_service_enqueue_ensures_queue_exists_before_submission(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="alpha")(run_topic)
        agents = self.runtime.AgentService()

        handle = await agents.enqueue("alpha", "hello")

        self.assertEqual(handle.workflow_id, "workflow-enqueued")
        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.assertEqual(
            self.DBOS.registered_queues,
            [("agent-runs", {"on_conflict": "never_update"})],
        )
        self.assertEqual(
            self.DBOS.enqueued_workflows,
            [("agent-runs", workflow_fn, "hello")],
        )
        self.assertEqual(
            self.DBOS.call_order,
            ["init", "launch", ("register_queue", "agent-runs")],
        )

    def test_worker_service_run_imports_modules_configures_queue_before_launch(self):
        sys.modules["customer_agent_module"] = types.ModuleType("customer_agent_module")
        self.decorators.register_agent(name="alpha")(lambda value: value)
        worker = self.runtime.WorkerService(
            agent_modules=["customer_agent_module"],
            queue_name="agent-runs",
            worker_concurrency=3,
            concurrency=9,
            keep_alive=False,
        )

        worker.run()

        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()
        self.assertEqual(
            self.DBOS.registered_queues[0][0],
            "agent-runs",
        )
        self.assertEqual(
            self.DBOS.registered_queues[0][1]["worker_concurrency"],
            3,
        )
        self.assertEqual(
            self.DBOS.registered_queues[0][1]["concurrency"],
            9,
        )
        self.assertEqual(self.DBOS.listened_queues, [["agent-runs"]])
        self.assertEqual(
            self.DBOS.call_order,
            [
                "init",
                ("listen_queues", ["agent-runs"]),
                "launch",
                ("register_queue", "agent-runs"),
            ],
        )

    def test_worker_service_requires_registered_agents(self):
        sys.modules["empty_agent_module"] = types.ModuleType("empty_agent_module")
        worker = self.runtime.WorkerService(
            agent_modules=["empty_agent_module"],
            keep_alive=False,
        )

        with self.assertRaisesRegex(RuntimeError, "No agents are registered"):
            worker.run()


class LoadWorkerTests(unittest.TestCase):
    def load_worker_module(self):
        fake_sdk = types.ModuleType("sdk")

        class Runtime:
            instances = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                Runtime.instances.append(self)

        class WorkerService:
            instances = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                WorkerService.instances.append(self)

            def run(self):
                self.ran = True

        fake_sdk.Runtime = Runtime
        fake_sdk.WorkerService = WorkerService
        with mock.patch.dict(sys.modules, {"sdk": fake_sdk}):
            module = load_module(
                "load_worker_under_test",
                "tests/load_testing/load_worker.py",
            )
        return module, Runtime, WorkerService

    def test_load_worker_passes_env_concurrency_to_worker_service(self):
        with mock.patch.dict(
            os.environ,
            {
                "LOAD_TEST_DB_URL": "postgres://load-test",
                "LOAD_TEST_RUNTIME_NAME": "load-runtime",
                "WORKER_CONCURRENCY": "3",
                "QUEUE_CONCURRENCY": "9",
            },
            clear=True,
        ):
            module, runtime, worker_service = self.load_worker_module()

            module.main()

        self.assertEqual(
            runtime.instances[0].kwargs,
            {"name": "load-runtime", "db_url": "postgres://load-test"},
        )
        self.assertEqual(worker_service.instances[0].kwargs["queue_name"], "agent-runs")
        self.assertEqual(
            worker_service.instances[0].kwargs["agent_modules"],
            ["tests.load_testing.synthetic_queue_agent"],
        )
        self.assertEqual(worker_service.instances[0].kwargs["worker_concurrency"], 3)
        self.assertEqual(worker_service.instances[0].kwargs["concurrency"], 9)
        self.assertTrue(worker_service.instances[0].ran)


class LoadAppTests(unittest.IsolatedAsyncioTestCase):
    def load_app_module(self):
        fake_agent_module = types.ModuleType("tests.load_testing.synthetic_queue_agent")
        fake_agent_module.SAMPLE_MESSAGE = "sleep=5"

        fake_sdk = types.ModuleType("sdk")

        class Runtime:
            instances = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                Runtime.instances.append(self)

            def start(self, **_kwargs):
                pass

        class AgentService:
            instances = []

            def __init__(self, runtime):
                self.runtime = runtime
                self.enqueued = []
                AgentService.instances.append(self)

            async def enqueue(self, name, input):
                self.enqueued.append((name, input))
                return types.SimpleNamespace(workflow_id="workflow-enqueued")

        fake_sdk.AgentService = AgentService
        fake_sdk.Runtime = Runtime
        fake_sdk.list_registered_agents = lambda: [
            types.SimpleNamespace(name="synthetic-queue-agent")
        ]

        modules = {
            "tests.load_testing.synthetic_queue_agent": fake_agent_module,
            "sdk": fake_sdk,
        }
        env = {
            "LOAD_TEST_DB_URL": "postgres://load-test",
            "LOAD_TEST_RUNTIME_NAME": "load-runtime",
        }
        with mock.patch.dict(sys.modules, modules), mock.patch.dict(
            os.environ, env, clear=True
        ):
            module = load_module(
                "load_app_under_test",
                "tests/load_testing/load_app.py",
            )
        return module, Runtime, AgentService

    async def test_load_app_accepts_synthetic_agent_only(self):
        module, runtime, agent_service = self.load_app_module()

        response = await module.create_run(
            module.RunRequest(agent="synthetic-queue-agent", input="sleep=12")
        )

        self.assertEqual(
            runtime.instances[0].kwargs,
            {"name": "load-runtime", "db_url": "postgres://load-test"},
        )
        self.assertEqual(response.workflow_id, "workflow-enqueued")
        self.assertEqual(response.agent, "synthetic-queue-agent")
        self.assertEqual(
            agent_service.instances[0].enqueued,
            [("synthetic-queue-agent", "sleep=12")],
        )

        with self.assertRaisesRegex(Exception, "Only 'synthetic-queue-agent'"):
            await module.create_run(
                module.RunRequest(agent="research-handoff-agent", input="hello")
            )


class LoadTestConfigTests(unittest.TestCase):
    def load_config_module(self):
        return load_module("load_test_config_under_test", "tests/load_testing/config.py")

    def test_load_test_config_requires_load_test_db_url(self):
        with mock.patch.dict(
            os.environ,
            {
                "DB_URL": "postgres://prod",
                "DBOS_SYSTEM_DATABASE_URL": "postgres://also-prod",
            },
            clear=True,
        ):
            config = self.load_config_module()
            config.ENV_FILE = ROOT / "__missing_load_test_env__"

            with self.assertRaisesRegex(RuntimeError, "LOAD_TEST_DB_URL is required"):
                config.load_load_test_config()

    def test_load_test_config_reads_dedicated_env(self):
        with mock.patch.dict(
            os.environ,
            {
                "LOAD_TEST_DB_URL": "postgres://load-test",
                "LOAD_TEST_RUNTIME_NAME": "custom-load-runtime",
            },
            clear=True,
        ):
            config = self.load_config_module()
            config.ENV_FILE = ROOT / "__missing_load_test_env__"

            resolved = config.load_load_test_config()

        self.assertEqual(resolved.db_url, "postgres://load-test")
        self.assertEqual(resolved.runtime_name, "custom-load-runtime")


class DemoRegistrationTests(unittest.TestCase):
    def setUp(self):
        install_agents_stubs()
        self.DBOS = install_decorator_stubs()
        self.decorators = load_module(
            "decorators_demo_under_test",
            "sdk/src/sdk/decorators.py",
        )
        sdk = types.ModuleType("sdk")
        sdk.register_agent = self.decorators.register_agent
        sdk.agent_runner = self.decorators.agent_runner
        sdk.logger = self.decorators.logger
        sdk.sleep = self.decorators.sleep
        sdk.step = self.decorators.step
        sys.modules["sdk"] = sdk

    def test_demo_imports_register_only_top_level_agents(self):
        load_module(
            "single_agent_demo_under_test",
            "example_customer_app/user_agents/single_agent_demo.py",
        )
        load_module(
            "multi_agent_demo_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        self.assertEqual(
            [agent.name for agent in self.decorators.list_registered_agents()],
            ["research-assistant", "travel-concierge"],
        )

    def test_synthetic_queue_agent_registers_for_local_load_tests(self):
        demo = load_module(
            "synthetic_queue_agent_under_test",
            "tests/load_testing/synthetic_queue_agent.py",
        )

        self.assertEqual(demo.parse_sleep_seconds("sleep=12"), 12)
        self.assertEqual(demo.parse_sleep_seconds("no explicit sleep"), 5)
        self.assertEqual(demo.parse_sleep_seconds("sleep=999"), 300)
        self.assertEqual(
            [agent.name for agent in self.decorators.list_registered_agents()],
            ["synthetic-queue-agent"],
        )

    def test_travel_request_normalizer_accepts_vague_prompt(self):
        demo = load_module(
            "multi_agent_demo_normalizer_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        normalized = demo.normalize_travel_request("book me a trip to Tokyo")

        self.assertEqual(normalized["origin"], "SFO")
        self.assertEqual(normalized["destination"], "Tokyo")
        self.assertEqual(normalized["depart_date"], "2026-07-10")
        self.assertEqual(normalized["return_date"], "2026-07-13")
        self.assertEqual(normalized["guests"], 2)
        self.assertEqual(normalized["budget"], 3000)

    def test_travel_request_normalizer_extracts_obvious_overrides(self):
        demo = load_module(
            "multi_agent_demo_complete_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        normalized = demo.normalize_travel_request(
            "Book a luxury trip to Paris from JFK for 4 people, "
            "departing 2026-08-01 and returning 2026-08-08, budget $5,500."
        )

        self.assertEqual(normalized["origin"], "JFK")
        self.assertEqual(normalized["destination"], "Paris")
        self.assertEqual(normalized["depart_date"], "2026-08-01")
        self.assertEqual(normalized["return_date"], "2026-08-08")
        self.assertEqual(normalized["guests"], 4)
        self.assertEqual(normalized["budget"], 5500)
        self.assertEqual(normalized["travel_style"], "luxury")

    def test_travel_request_normalizer_respects_edited_destination_prompts(self):
        demo = load_module(
            "multi_agent_demo_destinations_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        examples = {
            "booking your trip to washington": "Washington",
            "I want to visit Washington": "Washington",
            "Book me a trip to Washington DC from SFO for 2 people": "Washington DC",
        }

        for request, expected_destination in examples.items():
            with self.subTest(request=request):
                normalized = demo.normalize_travel_request(request)
                self.assertEqual(normalized["destination"], expected_destination)

    def test_travel_request_normalizer_defaults_destination_when_missing(self):
        demo = load_module(
            "multi_agent_demo_default_destination_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        normalized = demo.normalize_travel_request("book me a balanced trip from SFO for 2 people")

        self.assertEqual(normalized["destination"], "Tokyo")

    def test_travel_request_normalizer_extracts_place_name_origins(self):
        demo = load_module(
            "multi_agent_demo_origins_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        examples = [
            "book me a trip from massachusetts to canada",
            "book me a trip from Massachusetts to Canada",
        ]

        for request in examples:
            with self.subTest(request=request):
                normalized = demo.normalize_travel_request(request)
                self.assertEqual(normalized["origin"], "Massachusetts")
                self.assertEqual(normalized["destination"], "Canada")

    def test_travel_request_normalizer_defaults_origin_when_missing(self):
        demo = load_module(
            "multi_agent_demo_default_origin_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        normalized = demo.normalize_travel_request("book me a trip to Canada")

        self.assertEqual(normalized["origin"], "SFO")

    def test_guardrail_blocks_final_until_all_specialists_complete(self):
        demo = load_module(
            "multi_agent_demo_guardrail_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        self.assertEqual(demo.choose_guarded_next_action("final", {"flight"}), "hotel")
        self.assertEqual(
            demo.choose_guarded_next_action(
                "final",
                {"flight", "hotel", "local", "budget"},
            ),
            "final",
        )
        self.assertEqual(demo.choose_guarded_next_action("flight", {"flight"}), "hotel")

    def test_planner_action_can_be_extracted_from_json_or_prose(self):
        demo = load_module(
            "multi_agent_demo_planner_parse_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )

        self.assertEqual(demo.extract_planner_action('{"next_action": "hotel"}'), "hotel")
        self.assertEqual(
            demo.extract_planner_action("I recommend the budget specialist next."),
            "budget",
        )

    def test_queued_research_guardrail_blocks_final_until_all_phases_complete(self):
        demo = load_module(
            "queued_multi_agent_demo_guardrail_under_test",
            "example_customer_app/user_agents/queued_multi_agent_demo.py",
        )

        self.assertEqual(
            demo.choose_guarded_research_action("final", {"public_sources"}),
            "counterarguments",
        )
        self.assertEqual(
            demo.choose_guarded_research_action(
                "final",
                {"public_sources", "counterarguments", "evidence_brief"},
            ),
            "final",
        )
        self.assertEqual(
            demo.choose_guarded_research_action("public_sources", {"public_sources"}),
            "counterarguments",
        )
        self.assertEqual(
            demo.choose_guarded_research_action(
                "evidence_brief",
                {"public_sources"},
            ),
            "counterarguments",
        )

    def test_queued_research_action_can_be_extracted_from_json_or_prose(self):
        demo = load_module(
            "queued_multi_agent_demo_planner_parse_under_test",
            "example_customer_app/user_agents/queued_multi_agent_demo.py",
        )

        self.assertEqual(
            demo.extract_research_action('{"next_action": "public_sources"}'),
            "public_sources",
        )
        self.assertEqual(
            demo.extract_research_action("I recommend the evidence brief next."),
            "evidence brief",
        )

    def test_hotel_quotes_do_not_crash_without_request_marker(self):
        demo = load_module(
            "multi_agent_demo_no_crash_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )
        self.DBOS.workflow_id = "hotel-demo-1"

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(demo, "CRASH_MARKER_DIR", Path(tmpdir) / "markers"),
                mock.patch.object(demo, "CRASH_REQUEST_DIR", Path(tmpdir) / "requests"),
                mock.patch.object(demo.os, "kill") as kill,
            ):
                quotes = demo.get_hotel_quotes("Tokyo", "2026-07-10", "2026-07-13")

        kill.assert_not_called()
        self.assertIn("Market House Hotel", quotes)

    def test_travel_crash_is_only_armed_by_explicit_toggle(self):
        source_path = ROOT / "example_customer_app" / "main.py"
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source)
        helper = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_should_arm_travel_crash"
        )
        namespace: dict[str, object] = {}
        exec(compile(ast.Module([helper], []), str(source_path), "exec"), namespace)
        should_arm_travel_crash = namespace["_should_arm_travel_crash"]

        self.assertFalse(
            should_arm_travel_crash(
                "travel-concierge",
                crash_during_hotel=False,
            )
        )
        self.assertTrue(
            should_arm_travel_crash(
                "travel-concierge",
                crash_during_hotel=True,
            )
        )
        self.assertFalse(
            should_arm_travel_crash(
                "research-assistant",
                crash_during_hotel=True,
            )
        )
        self.assertNotIn("RANDOM_TRAVEL_CRASH_RATE", source)
        self.assertNotIn("random.random", source)

    def test_enterprise_branch_is_deterministic_from_account_signals(self):
        demo = load_module(
            "enterprise_onboarding_branch_under_test",
            "example_customer_app/user_agents/error_agent_demo.py",
        )

        standard = demo.normalize_onboarding_request(
            "Prepare onboarding notes for Acorn Software with 220 seats in the US."
        )
        enterprise = demo.normalize_onboarding_request(
            "Prepare onboarding notes for Northstar Health, an enterprise customer "
            "with 1800 seats across the US and EU. Procurement review required."
        )

        self.assertEqual(
            demo.determine_workflow_branch(standard, force_enterprise_branch=False),
            "standard_onboarding",
        )
        self.assertEqual(
            demo.determine_workflow_branch(enterprise, force_enterprise_branch=False),
            "enterprise_compliance",
        )
        self.assertEqual(
            demo.determine_workflow_branch(standard, force_enterprise_branch=True),
            "enterprise_compliance",
        )

    def test_enterprise_demo_helpers_append_and_strip_directives(self):
        demo = load_module(
            "enterprise_onboarding_directives_under_test",
            "example_customer_app/user_agents/error_agent_demo.py",
        )

        armed = demo.enable_enterprise_failure_demo("Start onboarding for Northstar Health")
        cleaned, force_branch, fail_handoff = demo._extract_demo_directives(armed)

        self.assertEqual(cleaned, "Start onboarding for Northstar Health")
        self.assertTrue(force_branch)
        self.assertTrue(fail_handoff)

    def test_enterprise_failure_is_only_armed_by_explicit_toggle(self):
        source_path = ROOT / "example_customer_app" / "main.py"
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source)
        helpers = {
            node.name: node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name
            in {"_should_fail_compliance_handoff", "_arm_enterprise_failure_input"}
        }
        namespace: dict[str, object] = {}
        error_agent_demo_stub = types.SimpleNamespace(
            enable_enterprise_compliance_branch=lambda value: f"{value}\n[force]",
            enable_compliance_handoff_failure=lambda value: f"{value}\n[fail]",
        )
        namespace["error_agent_demo"] = error_agent_demo_stub
        exec(
            compile(
                ast.Module(
                    [
                        helpers["_should_fail_compliance_handoff"],
                        helpers["_arm_enterprise_failure_input"],
                    ],
                    [],
                ),
                str(source_path),
                "exec",
            ),
            namespace,
        )

        self.assertFalse(
            namespace["_should_fail_compliance_handoff"](
                "research-assistant",
                fail_compliance_handoff=True,
            )
        )
        self.assertTrue(
            namespace["_should_fail_compliance_handoff"](
                "enterprise-onboarding-error-demo",
                fail_compliance_handoff=True,
            )
        )
        self.assertEqual(
            namespace["_arm_enterprise_failure_input"]("demo request"),
            "demo request\n[force]\n[fail]",
        )
        self.assertNotIn("force_enterprise_compliance:", source)

    def test_hotel_crash_marker_prevents_repeated_crashes(self):
        demo = load_module(
            "multi_agent_demo_crash_marker_under_test",
            "example_customer_app/user_agents/multi_agent_demo.py",
        )
        self.DBOS.workflow_id = "hotel-demo-2"

        with tempfile.TemporaryDirectory() as tmpdir:
            marker_dir = Path(tmpdir) / "markers"
            request_dir = Path(tmpdir) / "requests"
            with (
                mock.patch.object(demo, "CRASH_MARKER_DIR", marker_dir),
                mock.patch.object(demo, "CRASH_REQUEST_DIR", request_dir),
                mock.patch.object(demo.os, "kill") as kill,
            ):
                demo._request_hotel_crash(self.DBOS.workflow_id)
                demo._crash_once_during_hotel(self.DBOS.workflow_id)
                demo._request_hotel_crash(self.DBOS.workflow_id)
                demo._crash_once_during_hotel(self.DBOS.workflow_id)

                kill.assert_called_once()
                self.assertTrue((marker_dir / self.DBOS.workflow_id).exists())


class TracingTests(unittest.TestCase):
    def setUp(self):
        (
            self.AgentSpanData,
            self.TurnSpanData,
            self.FunctionSpanData,
            self.GenerationSpanData,
            self.ResponseSpanData,
            self.DBOS,
            self.add_trace_processor,
        ) = install_tracing_stubs()
        self.tracing = load_module("tracing_under_test", "sdk/src/sdk/tracing.py")

    def test_tool_outputs_preserve_falsy_values(self):
        processor = self.tracing.CheckpointTracingProcessor("postgresql://db")

        for value, expected in [(0, "0"), (False, "False"), ([], "[]"), (None, None), ("ok", "ok")]:
            with self.subTest(value=value):
                span = types.SimpleNamespace(
                    span_id=f"span-{value!r}",
                    span_data=self.FunctionSpanData(name="tool", input="{}", output=value),
                )
                with mock.patch.object(self.tracing, "_write_agent_event") as write:
                    processor.on_span_end(span)

                record = write.call_args.args[1]
                self.assertEqual(record["tool_result"], expected)

    def test_event_key_distinguishes_retry_step_identity(self):
        span = types.SimpleNamespace(span_id="span-1", trace_id="trace-1")
        base = {
            "workflow_id": "workflow-1",
            "span_id": "span-1",
            "event_type": "tool_call",
            "tool_name": "lookup",
        }

        first = self.tracing._event_key({**base, "step_id": 1}, span)
        retry = self.tracing._event_key({**base, "step_id": 2}, span)
        duplicate = self.tracing._event_key({**base, "step_id": 1}, span)

        self.assertNotEqual(first, retry)
        self.assertEqual(first, duplicate)

    def test_span_start_step_id_is_used_when_end_context_is_missing(self):
        processor = self.tracing.CheckpointTracingProcessor("postgresql://db")
        span = types.SimpleNamespace(
            span_id="span-1",
            span_data=self.FunctionSpanData(name="tool", input="{}", output="ok"),
        )

        self.DBOS.step_id = 11
        processor.on_span_start(span)
        self.DBOS.step_id = None
        with mock.patch.object(self.tracing, "_write_agent_event") as write:
            processor.on_span_end(span)

        record = write.call_args.args[1]
        self.assertEqual(record["step_id"], 11)

    def test_response_span_persists_llm_raw_io(self):
        processor = self.tracing.CheckpointTracingProcessor("postgresql://db")
        response = types.SimpleNamespace(
            id="resp_123",
            model="gpt-5.4-mini",
            output=[{"type": "message", "id": "msg_123"}],
        )
        span = types.SimpleNamespace(
            span_id="span-1",
            span_data=self.ResponseSpanData(
                input=[{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
                response=response,
                usage={"input_tokens": 10, "output_tokens": 5},
            ),
        )

        with mock.patch.object(self.tracing, "_write_agent_event") as write:
            processor.on_span_end(span)

        record = write.call_args.args[1]
        self.assertEqual(record["llm_input"], span.span_data.input)
        self.assertEqual(record["llm_output"], response.output)
        self.assertEqual(record["provider_response_id"], "resp_123")

    def test_response_span_inherits_agent_name_from_turn_span(self):
        processor = self.tracing.CheckpointTracingProcessor("postgresql://db")
        turn_span = types.SimpleNamespace(
            span_id="turn-1",
            parent_id=None,
            span_data=self.TurnSpanData(turn=1, agent_name="flight_researcher"),
        )
        response = types.SimpleNamespace(id="resp_123", model="gpt-5.4-mini", output=[])
        llm_span = types.SimpleNamespace(
            span_id="span-1",
            parent_id="turn-1",
            span_data=self.ResponseSpanData(response=response, input=[], usage={}),
        )

        processor.on_span_start(turn_span)
        processor.on_span_start(llm_span)
        with mock.patch.object(self.tracing, "_write_agent_event") as write:
            processor.on_span_end(llm_span)

        record = write.call_args.args[1]
        self.assertEqual(record["agent_name"], "flight_researcher")

    def test_response_span_falls_back_to_agent_span_name(self):
        processor = self.tracing.CheckpointTracingProcessor("postgresql://db")
        agent_span = types.SimpleNamespace(
            span_id="agent-1",
            parent_id=None,
            span_data=self.AgentSpanData(name="flight_researcher"),
        )
        response = types.SimpleNamespace(id="resp_123", model="gpt-5.4-mini", output=[])
        llm_span = types.SimpleNamespace(
            span_id="span-1",
            parent_id="agent-1",
            span_data=self.ResponseSpanData(response=response, input=[], usage={}),
        )

        processor.on_span_start(agent_span)
        processor.on_span_start(llm_span)
        with mock.patch.object(self.tracing, "_write_agent_event") as write:
            processor.on_span_end(llm_span)

        record = write.call_args.args[1]
        self.assertEqual(record["agent_name"], "flight_researcher")

    def test_function_span_inherits_agent_name_from_turn_span(self):
        processor = self.tracing.CheckpointTracingProcessor("postgresql://db")
        turn_span = types.SimpleNamespace(
            span_id="turn-1",
            parent_id=None,
            span_data=self.TurnSpanData(turn=1, agent_name="flight_researcher"),
        )
        tool_span = types.SimpleNamespace(
            span_id="tool-1",
            parent_id="turn-1",
            span_data=self.FunctionSpanData(name="get_flight_quotes", input="{}", output="ok"),
        )

        processor.on_span_start(turn_span)
        processor.on_span_start(tool_span)
        with mock.patch.object(self.tracing, "_write_agent_event") as write:
            processor.on_span_end(tool_span)

        record = write.call_args.args[1]
        self.assertEqual(record["event_type"], "tool_call")
        self.assertEqual(record["agent_name"], "flight_researcher")

    def test_function_span_falls_back_to_agent_span_name(self):
        processor = self.tracing.CheckpointTracingProcessor("postgresql://db")
        agent_span = types.SimpleNamespace(
            span_id="agent-1",
            parent_id=None,
            span_data=self.AgentSpanData(name="travel-concierge-planner"),
        )
        tool_span = types.SimpleNamespace(
            span_id="tool-1",
            parent_id="agent-1",
            span_data=self.FunctionSpanData(name="record_planning_decision", input="{}", output="ok"),
        )

        processor.on_span_start(agent_span)
        processor.on_span_start(tool_span)
        with mock.patch.object(self.tracing, "_write_agent_event") as write:
            processor.on_span_end(tool_span)

        record = write.call_args.args[1]
        self.assertEqual(record["event_type"], "tool_call")
        self.assertEqual(record["agent_name"], "travel-concierge-planner")

    def test_to_json_compatible_handles_model_dump_and_lists(self):
        class FakeModel:
            def __init__(self, payload):
                self.payload = payload

            def model_dump(self, mode="json", exclude_unset=True):
                self.asserted_mode = mode
                self.asserted_exclude_unset = exclude_unset
                return self.payload

        model = FakeModel({"type": "message", "id": "msg_123"})
        converted = self.tracing._to_json_compatible([model, {"raw": True}, None])

        self.assertEqual(
            converted,
            [{"type": "message", "id": "msg_123"}, {"raw": True}, None],
        )
        self.assertEqual(model.asserted_mode, "json")
        self.assertTrue(model.asserted_exclude_unset)

    def test_connect_kwargs_include_short_timeouts(self):
        kwargs = self.tracing._connect_kwargs()

        self.assertEqual(kwargs["connect_timeout"], 3)
        self.assertIn("statement_timeout=3000", kwargs["options"])
        self.assertIn("lock_timeout=1000", kwargs["options"])

    def test_connection_pool_is_reused_and_bounded(self):
        fake_pool = object()
        with mock.patch.object(
            self.tracing.psycopg2.pool,
            "ThreadedConnectionPool",
            return_value=fake_pool,
        ) as pool_cls:
            first = self.tracing._get_pool("postgresql://db")
            second = self.tracing._get_pool("postgresql://db")

        self.assertIs(first, fake_pool)
        self.assertIs(second, fake_pool)
        pool_cls.assert_called_once()
        self.assertEqual(pool_cls.call_args.args[:3], (1, 4, "postgresql://db"))

    def test_register_checkpoint_processor_is_idempotent(self):
        with mock.patch.object(self.tracing, "ensure_tables") as ensure_tables:
            self.tracing.register_checkpoint_tracing_processor("postgresql://db")
            self.tracing.register_checkpoint_tracing_processor("postgresql://db")

        ensure_tables.assert_called_once_with("postgresql://db")
        self.add_trace_processor.assert_called_once()


if __name__ == "__main__":
    unittest.main()
