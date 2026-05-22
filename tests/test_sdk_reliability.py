import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


queries = load_module("queries_under_test", "sdk/src/sdk/queries.py")


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
        self.assertIsNone(records[0]["step_error"])
        self.assertIsNone(records[0]["child_workflow_id"])

    def test_build_step_records_carries_dbos_native_output_for_plain_steps(self):
        steps = [
            {
                "function_id": 1,
                "function_name": "normalize_travel_request",
                "output": {"destination": "Tokyo", "guests": 2},
                "error": None,
                "child_workflow_id": None,
            }
        ]

        records = queries.build_step_records(steps, [])

        self.assertEqual(records[0]["event_type"], "step")
        self.assertEqual(
            records[0]["step_output"],
            {"destination": "Tokyo", "guests": 2},
        )
        self.assertIsNone(records[0]["step_error"])
        self.assertIsNone(records[0]["child_workflow_id"])

    def test_build_step_records_stringifies_dbos_native_errors(self):
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
        self.assertEqual(records[0]["step_error"], "bad lookup")
        self.assertEqual(records[0]["child_workflow_id"], "wf-child-1")

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
        started_workflows = []

        def __init__(self, config=None):
            self.config = config
            DBOS.init_calls.append(config)

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

    class DBOSRunner:
        pass

    dbos.DBOS = DBOS
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

    def function_tool(fn):
        fn._is_function_tool = True
        return fn

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
        self.DBOS = install_decorator_stubs()
        self.decorators = load_module("decorators_registry_under_test", "sdk/src/sdk/decorators.py")

    def test_agent_decorator_registers_named_workflow(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="research-assistant")(run_topic)

        registered = self.decorators.get_registered_agent("research-assistant")
        self.assertEqual(registered.name, "research-assistant")
        self.assertIs(registered.workflow, workflow_fn)
        self.assertEqual(workflow_fn._dbos_workflow_name, "research-assistant")

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

    def test_init_is_idempotent_and_reads_embedded_env(self):
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
            self.decorators.init()
            self.decorators.init()

        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()
        self.assertEqual(self.DBOS.init_calls[0]["name"], "embedded-app")
        self.assertEqual(
            self.DBOS.init_calls[0]["system_database_url"],
            "postgres://primary",
        )
        self.assertEqual(self.DBOS.init_calls[0]["conductor_key"], "key-1")

    async def test_start_agent_initializes_once_and_starts_registered_workflow(self):
        async def run_topic(topic: str) -> str:
            return topic

        workflow_fn = self.decorators.register_agent(name="alpha")(run_topic)

        first = await self.decorators.start_agent("alpha", "hello")
        second = await self.decorators.start_agent("alpha", "again")

        self.assertEqual(first.workflow_id, "workflow-started")
        self.assertEqual(second.workflow_id, "workflow-started")
        self.assertEqual(len(self.DBOS.init_calls), 1)
        self.DBOS.launch.assert_called_once()
        self.assertEqual(
            self.DBOS.started_workflows,
            [(workflow_fn, "hello"), (workflow_fn, "again")],
        )


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
        sdk.agentic_runner = self.decorators.agentic_runner
        sdk.logger = self.decorators.logger
        sdk.sleep = self.decorators.sleep
        sdk.step = self.decorators.step
        sys.modules["sdk"] = sdk

    def test_demo_imports_register_only_top_level_agents(self):
        load_module("single_agent_demo_under_test", "user_agents/single_agent_demo.py")
        load_module("multi_agent_demo_under_test", "user_agents/multi_agent_demo.py")

        self.assertEqual(
            [agent.name for agent in self.decorators.list_registered_agents()],
            ["research-assistant", "travel-concierge"],
        )

    def test_travel_request_normalizer_accepts_vague_prompt(self):
        demo = load_module("multi_agent_demo_normalizer_under_test", "user_agents/multi_agent_demo.py")

        normalized = demo.normalize_travel_request("book me a trip to Tokyo")

        self.assertEqual(normalized["origin"], "SFO")
        self.assertEqual(normalized["destination"], "Tokyo")
        self.assertEqual(normalized["depart_date"], "2026-07-10")
        self.assertEqual(normalized["return_date"], "2026-07-13")
        self.assertEqual(normalized["guests"], 2)
        self.assertEqual(normalized["budget"], 3000)

    def test_travel_request_normalizer_extracts_obvious_overrides(self):
        demo = load_module("multi_agent_demo_complete_under_test", "user_agents/multi_agent_demo.py")

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
        demo = load_module("multi_agent_demo_destinations_under_test", "user_agents/multi_agent_demo.py")

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
        demo = load_module("multi_agent_demo_default_destination_under_test", "user_agents/multi_agent_demo.py")

        normalized = demo.normalize_travel_request("book me a balanced trip from SFO for 2 people")

        self.assertEqual(normalized["destination"], "Tokyo")

    def test_travel_request_normalizer_extracts_place_name_origins(self):
        demo = load_module("multi_agent_demo_origins_under_test", "user_agents/multi_agent_demo.py")

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
        demo = load_module("multi_agent_demo_default_origin_under_test", "user_agents/multi_agent_demo.py")

        normalized = demo.normalize_travel_request("book me a trip to Canada")

        self.assertEqual(normalized["origin"], "SFO")

    def test_guardrail_blocks_final_until_all_specialists_complete(self):
        demo = load_module("multi_agent_demo_guardrail_under_test", "user_agents/multi_agent_demo.py")

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
        demo = load_module("multi_agent_demo_planner_parse_under_test", "user_agents/multi_agent_demo.py")

        self.assertEqual(demo.extract_planner_action('{"next_action": "hotel"}'), "hotel")
        self.assertEqual(
            demo.extract_planner_action("I recommend the budget specialist next."),
            "budget",
        )

    def test_hotel_quotes_do_not_crash_without_request_marker(self):
        demo = load_module("multi_agent_demo_no_crash_under_test", "user_agents/multi_agent_demo.py")
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

    def test_hotel_crash_marker_prevents_repeated_crashes(self):
        demo = load_module("multi_agent_demo_crash_marker_under_test", "user_agents/multi_agent_demo.py")
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
