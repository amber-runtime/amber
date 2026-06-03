import importlib.util
import os
import pickle
import sys
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SDK_PACKAGE_ROOT = ROOT / "sdk"


def ensure_sdk_package_root():
    if str(SDK_PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(SDK_PACKAGE_ROOT))


def clear_amber_modules():
    for module_name in ("amber.runtime", "amber.decorators", "amber"):
        sys.modules.pop(module_name, None)


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


queries = load_module("queries_under_test", "sdk/amber/dashboard/queries.py")


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


class AgentRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_amber_modules()
        self.DBOS = install_decorator_stubs()
        self.env_patcher = mock.patch.dict(
            os.environ,
            {"DB_URL": "sqlite:///test"},
            clear=False,
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        ensure_sdk_package_root()
        self.decorators = importlib.import_module("amber.decorators")
        self.runtime = importlib.import_module("amber.runtime")

    def tearDown(self):
        self.env_patcher.stop()

    def test_agent_decorator_registers_named_workflow(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="research-assistant")(run_topic)

        registered = self.decorators.get_registered_agent("research-assistant")
        self.assertEqual(registered.name, "research-assistant")
        self.assertIs(registered.workflow, workflow_fn)
        self.assertFalse(hasattr(registered, "queued"))
        self.assertEqual(workflow_fn._dbos_workflow_name, "research-assistant")

    def test_agent_decorator_rejects_queued_argument(self):
        async def run_topic(topic: str) -> str:
            return topic

        with self.assertRaisesRegex(TypeError, "queued"):
            self.decorators.register_agent(
                name="research-handoff-agent",
                **{"queued": True},
            )(run_topic)

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

    async def test_agent_runner_sanitizes_pickling_unsafe_exceptions(self):
        def closure():
            return "not pickleable"

        unsafe = RuntimeError("tool failed")
        unsafe.bad_attr = closure
        self.assertRaises(Exception, pickle.dumps, unsafe)

        self.decorators.DBOSRunner.run = mock.AsyncMock(side_effect=unsafe)

        with self.assertRaises(self.decorators.AgentRunError) as ctx:
            await self.decorators.agent_runner(starting_agent="alpha", input="hello")

        self.assertEqual(str(ctx.exception), "tool failed")
        self.assertEqual(ctx.exception.original_type, "RuntimeError")
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)
        pickle.dumps(ctx.exception)

    async def test_agent_runner_preserves_clean_message_for_wrapped_errors(self):
        wrapped = RuntimeError(
            "Error running tool commit_compliance_handoff: Compliance ticket schema mismatch blocked external handoff."
        )
        self.decorators.DBOSRunner.run = mock.AsyncMock(side_effect=wrapped)

        with self.assertRaises(self.decorators.AgentRunError) as ctx:
            await self.decorators.agent_runner(starting_agent="alpha", input="hello")

        self.assertEqual(
            str(ctx.exception),
            "Error running tool commit_compliance_handoff: Compliance ticket schema mismatch blocked external handoff.",
        )
        self.assertEqual(ctx.exception.original_type, "RuntimeError")

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

    async def test_agent_service_run_inline_initializes_once_and_starts_registered_workflow(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="alpha")(run_topic)
        agents = self.runtime.AgentService()

        first = await agents.run_inline("alpha", "hello")
        second = await agents.run_inline("alpha", "again")

        self.assertEqual(first.workflow_id, "workflow-started")
        self.assertEqual(second.workflow_id, "workflow-started")
        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()
        self.assertEqual(
            self.DBOS.started_workflows,
            [(workflow_fn, "hello"), (workflow_fn, "again")],
        )

    async def test_agent_service_start_enqueues_registered_agent(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="alpha")(run_topic)
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

    async def test_agent_service_start_queue_name_override_applies(self):
        async def run_topic(topic: str) -> str:
            return topic

        queued_workflow = self.decorators.register_agent(name="queued")(run_topic)
        other_workflow = self.decorators.register_agent(name="other")(run_topic)
        agents = self.runtime.AgentService()

        queued_handle = await agents.start("queued", "queued-input", queue_name="slow-lane")
        other_handle = await agents.start("other", "other-input", queue_name="slow-lane")

        self.assertEqual(queued_handle.workflow_id, "workflow-enqueued")
        self.assertEqual(other_handle.workflow_id, "workflow-enqueued")
        self.assertEqual(
            self.DBOS.registered_queues,
            [
                ("slow-lane", {"on_conflict": "never_update"}),
                ("slow-lane", {"on_conflict": "never_update"}),
            ],
        )
        self.assertEqual(
            self.DBOS.enqueued_workflows,
            [
                ("slow-lane", queued_workflow, "queued-input"),
                ("slow-lane", other_workflow, "other-input"),
            ],
        )
        self.assertEqual(self.DBOS.started_workflows, [])

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

    def test_agent_runtime_defaults_to_queue_first_worker_settings(self):
        agent_runtime = self.runtime.AgentRuntime()

        self.assertEqual(agent_runtime.queue_name, "agent-runs")
        self.assertEqual(agent_runtime.worker_concurrency, 8)
        self.assertIsNone(agent_runtime.queue_concurrency)
        self.assertIsInstance(agent_runtime.agents, self.runtime.AgentService)

    async def test_agent_runtime_api_lifespan_disables_queue_listeners(self):
        agent_runtime = self.runtime.AgentRuntime()

        async with agent_runtime.api_lifespan()(object()):
            pass

        self.assertEqual(self.DBOS.listened_queues, [[]])
        self.assertEqual(
            self.DBOS.call_order,
            ["init", ("listen_queues", []), "launch"],
        )

    def test_agent_runtime_rejects_global_concurrency_below_worker_concurrency(self):
        with self.assertRaisesRegex(
            ValueError,
            "queue_concurrency must be greater than or equal to worker_concurrency",
        ):
            self.runtime.AgentRuntime(worker_concurrency=5, queue_concurrency=4)

    def test_agent_runtime_run_worker_uses_configured_queue_settings(self):
        self.decorators.register_agent(name="alpha")(lambda value: value)
        agent_runtime = self.runtime.AgentRuntime(
            queue_name="slow-lane",
            worker_concurrency=4,
            queue_concurrency=12,
        )

        agent_runtime.run_worker(keep_alive=False)

        self.assertEqual(self.DBOS.listened_queues, [["slow-lane"]])
        self.assertEqual(self.DBOS.registered_queues[0][0], "slow-lane")
        self.assertEqual(self.DBOS.registered_queues[0][1]["worker_concurrency"], 4)
        self.assertEqual(self.DBOS.registered_queues[0][1]["concurrency"], 12)


class SDKWorkerEntrypointTests(unittest.TestCase):
    def load_worker_entrypoint(self):
        return load_module("sdk_worker_under_test", "sdk/amber/worker.py")

    def test_worker_entrypoint_loads_runtime_target_and_runs_worker(self):
        module = types.ModuleType("customer_app.main")
        agent_runtime = mock.Mock()
        module.agent_runtime = agent_runtime

        with mock.patch.dict(sys.modules, {"customer_app.main": module}):
            worker_entrypoint = self.load_worker_entrypoint()
            result = worker_entrypoint.main(["customer_app.main:agent_runtime"])

        self.assertEqual(result, 0)
        agent_runtime.run_worker.assert_called_once_with()

    def test_worker_entrypoint_rejects_invalid_target_format(self):
        worker_entrypoint = self.load_worker_entrypoint()

        with self.assertRaisesRegex(ValueError, "module:object"):
            worker_entrypoint._load_target("customer_app.main")

    def test_worker_entrypoint_requires_run_worker_method(self):
        module = types.ModuleType("customer_app.main")
        module.agent_runtime = object()

        with mock.patch.dict(sys.modules, {"customer_app.main": module}):
            worker_entrypoint = self.load_worker_entrypoint()
            with self.assertRaisesRegex(SystemExit, "run_worker"):
                worker_entrypoint.main(["customer_app.main:agent_runtime"])


class LoadWorkerTests(unittest.TestCase):
    def load_worker_module(self):
        fake_amber = types.ModuleType("amber")

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

        fake_amber.Runtime = Runtime
        fake_amber.WorkerService = WorkerService
        with mock.patch.dict(sys.modules, {"amber": fake_amber}):
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

        fake_amber = types.ModuleType("amber")

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

            async def start(self, name, input):
                self.enqueued.append((name, input))
                return types.SimpleNamespace(workflow_id="workflow-enqueued")

        fake_amber.AgentService = AgentService
        fake_amber.Runtime = Runtime
        fake_amber.list_registered_agents = lambda: [
            types.SimpleNamespace(name="synthetic-queue-agent")
        ]

        modules = {
            "tests.load_testing.synthetic_queue_agent": fake_agent_module,
            "amber": fake_amber,
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


class SyntheticQueueAgentTests(unittest.TestCase):
    def test_synthetic_queue_agent_registers_for_local_load_tests(self):
        registered_agents = []
        fake_amber = types.ModuleType("amber")
        fake_amber.logger = mock.Mock()

        def register_agent(*, name):
            def decorator(fn):
                registered_agents.append(types.SimpleNamespace(name=name, workflow=fn))
                return fn

            return decorator

        async def sleep(_seconds):
            return None

        fake_amber.register_agent = register_agent
        fake_amber.sleep = sleep

        with mock.patch.dict(sys.modules, {"amber": fake_amber}):
            demo = load_module(
                "synthetic_queue_agent_under_test",
                "tests/load_testing/synthetic_queue_agent.py",
            )

        self.assertEqual(demo.parse_sleep_seconds("sleep=12"), 12)
        self.assertEqual(demo.parse_sleep_seconds("no explicit sleep"), 5)
        self.assertEqual(demo.parse_sleep_seconds("sleep=999"), 300)
        self.assertEqual(
            [agent.name for agent in registered_agents],
            ["synthetic-queue-agent"],
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
        self.tracing = load_module("tracing_under_test", "sdk/amber/tracing.py")

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

    def test_connect_kwargs_include_short_connect_timeout_without_startup_options(self):
        kwargs = self.tracing._connect_kwargs()

        self.assertEqual(kwargs["connect_timeout"], 3)
        self.assertNotIn("options", kwargs)

    def test_configure_connection_timeouts_sets_session_values_after_connect(self):
        conn = mock.MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value

        self.tracing._configure_connection_timeouts(conn)

        cursor.execute.assert_has_calls(
            [
                mock.call("SET statement_timeout = %s", (3000,)),
                mock.call("SET lock_timeout = %s", (1000,)),
            ]
        )

    def test_ensure_tables_configures_timeouts_after_connect(self):
        conn = mock.MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with mock.patch.object(
            self.tracing.psycopg2,
            "connect",
            return_value=conn,
        ) as connect:
            self.tracing.ensure_tables("postgresql://db")

        connect.assert_called_once_with("postgresql://db", connect_timeout=3)
        self.assertEqual(
            cursor.execute.call_args_list[:2],
            [
                mock.call("SET statement_timeout = %s", (3000,)),
                mock.call("SET lock_timeout = %s", (1000,)),
            ],
        )
        conn.commit.assert_called_once()

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
