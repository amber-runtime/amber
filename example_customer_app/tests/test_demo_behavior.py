import ast
import asyncio
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from example_customer_app.tests.support import (
    ROOT,
    clear_amber_modules,
    install_agents_stubs,
    install_amber_stub,
    load_module,
)


class DemoRegistrationTests(unittest.TestCase):
    def setUp(self):
        clear_amber_modules()
        install_agents_stubs()
        self.amber, self.DBOS = install_amber_stub()

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
            [agent.name for agent in self.amber.list_registered_agents()],
            ["research-assistant", "travel-concierge"],
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
            "another_multi_agent_demo_guardrail_under_test",
            "example_customer_app/user_agents/another_multi_agent_demo.py",
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
            "another_multi_agent_demo_planner_parse_under_test",
            "example_customer_app/user_agents/another_multi_agent_demo.py",
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
                mock.patch.object(demo, "_crash_db_url", return_value=None),
                mock.patch.object(demo.os, "_exit") as hard_exit,
            ):
                quotes = demo.get_hotel_quotes("Tokyo", "2026-07-10", "2026-07-13")

        hard_exit.assert_not_called()
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

    def test_account_research_helpers_append_and_strip_directives(self):
        demo = load_module(
            "account_research_error_demo_directives_under_test",
            "example_customer_app/user_agents/account_research_error_demo.py",
        )

        armed = demo.enable_account_research_failure_demo(
            "Research Meridian Logistics before our enterprise call."
        )
        cleaned, force_branch, trigger_ratelimit = demo._extract_demo_directives(armed)

        self.assertEqual(
            cleaned,
            "Research Meridian Logistics before our enterprise call.",
        )
        self.assertTrue(force_branch)
        self.assertTrue(trigger_ratelimit)

    def test_account_research_deep_scan_fails_on_third_query_when_armed(self):
        demo = load_module(
            "account_research_error_demo_failure_under_test",
            "example_customer_app/user_agents/account_research_error_demo.py",
        )
        self.DBOS.workflow_id = "account-research-deep-scan-fail"
        demo._ratelimit_workflows.add(self.DBOS.workflow_id)

        with mock.patch.object(
            demo.time,
            "monotonic",
            side_effect=[i / 100 for i in range(40)],
        ):
            with self.assertRaisesRegex(
                ConnectionError,
                "Remote end closed connection without response",
            ):
                demo.scrape_deep_competitive_signals(
                    "Meridian Logistics",
                    "logistics",
                )

    def test_account_research_deep_scan_succeeds_without_ratelimit(self):
        demo = load_module(
            "account_research_error_demo_success_under_test",
            "example_customer_app/user_agents/account_research_error_demo.py",
        )
        self.DBOS.workflow_id = "account-research-deep-scan-ok"
        demo._ratelimit_workflows.clear()

        with mock.patch.object(
            demo.time,
            "monotonic",
            side_effect=[i / 100 for i in range(80)],
        ):
            result = demo.scrape_deep_competitive_signals(
                "Meridian Logistics",
                "logistics",
            )

        parsed = json.loads(result)
        self.assertEqual(parsed["query_count"], 5)
        self.assertEqual(len(parsed["signals"]), 5)

    def test_account_research_email_receipt_uses_workflow_id(self):
        demo = load_module(
            "account_research_error_demo_receipt_under_test",
            "example_customer_app/user_agents/account_research_error_demo.py",
        )
        self.DBOS.workflow_id = "account-research-1"

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_dir = Path(tmpdir)
            with mock.patch.object(demo, "OUTREACH_RECEIPT_DIR", receipt_dir):
                receipt = demo.send_account_brief_email(
                    "ae@example.com",
                    "Meridian Logistics",
                    "Short brief",
                )

            receipt_path = receipt_dir / "account-research-1.json"
            self.assertTrue(receipt_path.exists())
            parsed = json.loads(receipt)
            self.assertEqual(parsed["workflow_id"], "account-research-1")
            self.assertEqual(parsed["status"], "sent")

    def test_account_research_workflow_propagates_failure_when_armed(self):
        demo = load_module(
            "account_research_error_demo_workflow_failure_under_test",
            "example_customer_app/user_agents/account_research_error_demo.py",
        )

        async def fake_run_standard_research(_account):
            return {
                "news_research": '{"summary":"news"}',
                "market_positioning": '{"summary":"pricing"}',
                "tech_stack_signals": '{"summary":"tech"}',
            }

        async def fake_agent_runner(*, starting_agent, input):
            name = starting_agent.name
            if name == "brief_compiler":
                return types.SimpleNamespace(final_output="brief")
            if name == "outreach_operator":
                return types.SimpleNamespace(
                    final_output=demo.send_account_brief_email(
                        "ae@amber-demo.example",
                        "Meridian Logistics",
                        "brief",
                    )
                )
            if name == "deep_scan_agent":
                return types.SimpleNamespace(
                    final_output=demo.scrape_deep_competitive_signals(
                        "Meridian Logistics",
                        "logistics",
                    )
                )
            raise AssertionError(f"Unexpected agent_runner call for {name}: {input}")

        with (
            mock.patch.object(demo, "_run_standard_research", side_effect=fake_run_standard_research),
            mock.patch.object(demo, "agent_runner", side_effect=fake_agent_runner),
            self.assertRaisesRegex(
                ConnectionError,
                "Remote end closed connection without response",
            ),
        ):
            asyncio.run(
                demo.account_research_error_demo(
                    demo.enable_account_research_failure_demo(demo.SAMPLE_INPUT)
                )
            )

    def test_account_research_failure_toggle_supports_canonical_demo(self):
        source_path = ROOT / "example_customer_app" / "main.py"
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source)
        helpers = {
            node.name: node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name
            in {
                "_should_arm_account_research_ratelimit",
                "_arm_account_research_ratelimit_input",
            }
        }
        namespace: dict[str, object] = {}
        namespace["account_research_error_demo"] = types.SimpleNamespace(
            enable_account_research_failure_demo=lambda value: f"{value}\n[armed]",
        )
        exec(
            compile(
                ast.Module(
                    [
                        helpers["_should_arm_account_research_ratelimit"],
                        helpers["_arm_account_research_ratelimit_input"],
                    ],
                    [],
                ),
                str(source_path),
                "exec",
            ),
            namespace,
        )

        self.assertTrue(
            namespace["_should_arm_account_research_ratelimit"](
                "account-research-error-demo",
                trigger_account_research_ratelimit=True,
            )
        )
        self.assertFalse(
            namespace["_should_arm_account_research_ratelimit"](
                "research-assistant",
                trigger_account_research_ratelimit=True,
            )
        )
        self.assertEqual(
            namespace["_arm_account_research_ratelimit_input"]("demo request"),
            "demo request\n[armed]",
        )

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
                mock.patch.object(demo, "_crash_db_url", return_value=None),
                mock.patch.object(demo.os, "_exit") as hard_exit,
            ):
                demo._request_hotel_crash(self.DBOS.workflow_id)
                demo._crash_once_during_hotel(self.DBOS.workflow_id)
                demo._request_hotel_crash(self.DBOS.workflow_id)
                demo._crash_once_during_hotel(self.DBOS.workflow_id)

                hard_exit.assert_called_once_with(42)
                self.assertTrue((marker_dir / self.DBOS.workflow_id).exists())
