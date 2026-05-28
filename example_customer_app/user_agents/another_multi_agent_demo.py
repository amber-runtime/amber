from __future__ import annotations

import json
import re
from typing import Any

from agents import Agent, function_tool

from sdk import register_agent, agent_runner, logger, step

SAMPLE_MESSAGE = (
    "Prepare a deep research memo on whether midsize logistics operators should adopt "
    "AI dispatch copilots over the next 18 months. Gather source material, surface "
    "counterarguments, and end with a recommendation plus open risks."
)
HANDOFF_NOTE = (
    "DBOS durably stores workflow and step execution. The dashboard enriches that with "
    "agent events from the SDK. Planner and step events are expected on successful "
    "queued runs."
)
REQUIRED_RESEARCH_PHASES = ("public_sources", "counterarguments", "evidence_brief")
MAX_RESEARCH_DECISIONS = 5


def _json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


@step()
def _search_public_sources_step(topic: str) -> dict[str, Any]:
    logger.info("Collecting public source pack for topic: %s", topic)
    return {
        "topic": topic,
        "sources": [
            {
                "title": "Fleet operators pilot AI dispatch copilots",
                "kind": "trade_report",
                "claim": "Dispatch copilots reduce manual scheduling load but need strong ops oversight.",
            },
            {
                "title": "Broker margin pressure and scheduling delays in regional freight",
                "kind": "industry_brief",
                "claim": "Midsize operators adopt automation when labor gaps outweigh software integration costs.",
            },
            {
                "title": "Transportation CIO benchmark survey",
                "kind": "survey",
                "claim": "Operations leaders want measurable ETA accuracy gains before scaling copilots fleet-wide.",
            },
        ],
        "open_questions": [
            "How quickly do deployment costs show up in operating margin?",
            "What operational guardrails are required before dispatch autonomy is trusted?",
        ],
    }


@function_tool
def search_public_sources(topic: str) -> dict[str, Any]:
    return _search_public_sources_step(topic)


@step()
def _gather_counterarguments_step(topic: str) -> dict[str, Any]:
    logger.info("Collecting counterarguments for topic: %s", topic)
    return {
        "topic": topic,
        "counterarguments": [
            "Dispatch copilots can amplify bad data quality if TMS integrations are incomplete.",
            "Change-management costs may exceed productivity gains for teams with low workflow standardization.",
            "Vendors often overstate short-term ROI relative to the training burden on dispatch managers.",
        ],
        "risks": [
            "False confidence in ETA predictions can trigger customer-facing service failures.",
            "Tool sprawl can create fragmented incident response when multiple copilots own adjacent workflows.",
        ],
    }


@function_tool
def gather_counterarguments(topic: str) -> dict[str, Any]:
    return _gather_counterarguments_step(topic)


@step()
def _assemble_evidence_brief_step(public_pack: str, counterarguments: str) -> dict[str, Any]:
    logger.info("Assembling evidence brief from upstream specialist outputs")
    return {
        "evidence_summary": [
            "Operators are interested in copilots when they reduce dispatcher workload without changing customer SLAs.",
            "Pilot success depends on clean workflow instrumentation, exception review, and clear human override paths.",
            "ROI is strongest when copilots improve the speed of triage rather than attempt full autonomy immediately.",
        ],
        "public_pack_excerpt": public_pack[:500],
        "counterarguments_excerpt": counterarguments[:500],
        "recommended_memo_shape": [
            "Current market signal",
            "Adoption constraints",
            "Operational safeguards",
            "Recommendation and open risks",
        ],
    }


@function_tool
def assemble_evidence_brief(public_pack: str, counterarguments: str) -> dict[str, Any]:
    return _assemble_evidence_brief_step(public_pack, counterarguments)


@function_tool
@step()
def record_research_decision(next_action: str, rationale: str) -> str:
    """Record the coordinator's next research phase choice."""
    return _json({"next_action": next_action, "rationale": rationale})


def _parse_json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        return {}

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def extract_research_action(planner_output: str) -> str:
    decision = _parse_json_object(planner_output)
    action = str(decision.get("next_action", "")).strip()
    if action:
        return action

    match = re.search(
        r"\b(public sources|public_sources|sources|source collection|"
        r"counterarguments|counter arguments|risks|evidence brief|"
        r"evidence_brief|brief|final|finish|done)\b",
        planner_output,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _first_missing_research_phase(completed: set[str]) -> str:
    for phase in REQUIRED_RESEARCH_PHASES:
        if phase not in completed:
            return phase
    return "final"


def choose_guarded_research_action(raw_action: str, completed: set[str]) -> str:
    action = raw_action.strip().lower().replace("-", "_")
    action = re.sub(r"\s+", "_", action)
    aliases = {
        "public": "public_sources",
        "sources": "public_sources",
        "source": "public_sources",
        "source_collection": "public_sources",
        "public_source": "public_sources",
        "public_sources": "public_sources",
        "counterargument": "counterarguments",
        "counterarguments": "counterarguments",
        "counter_arguments": "counterarguments",
        "risks": "counterarguments",
        "risk": "counterarguments",
        "brief": "evidence_brief",
        "evidence": "evidence_brief",
        "evidence_brief": "evidence_brief",
        "done": "final",
        "finish": "final",
    }
    action = aliases.get(action, action)

    if action == "final":
        return (
            "final"
            if len(completed) == len(REQUIRED_RESEARCH_PHASES)
            else _first_missing_research_phase(completed)
        )
    if action not in REQUIRED_RESEARCH_PHASES:
        return _first_missing_research_phase(completed)
    if action in completed:
        return _first_missing_research_phase(completed)
    has_inputs_for_brief = {"public_sources", "counterarguments"}.issubset(completed)
    if action == "evidence_brief" and not has_inputs_for_brief:
        return _first_missing_research_phase(completed)
    return action


research_planner = Agent(
    name="research_planner",
    instructions=(
        "You are the research workflow planner. Choose exactly one next action from "
        "public_sources, counterarguments, evidence_brief, or final. Use "
        "record_research_decision exactly once. Prefer the most useful missing phase. "
        "Do not choose evidence_brief until public_sources and counterarguments are "
        "complete. Do not choose final until all phases are complete."
    ),
    tools=[record_research_decision],
)

synthesis_writer = Agent(
    name="synthesis_writer",
    instructions=(
        "You are the synthesis specialist. Build a crisp research memo that cites the "
        "completed evidence package, highlights disagreements, and ends with a "
        "decision-ready recommendation plus unresolved risks."
    ),
)


def _research_phase_prompt(
    topic: str,
    completed: set[str],
    findings: dict[str, Any],
) -> str:
    return (
        "Choose the next phase for this queued research workflow.\n\n"
        f"Required phases: {', '.join(REQUIRED_RESEARCH_PHASES)}\n"
        f"Completed phases: {', '.join(sorted(completed)) or 'none'}\n"
        f"Research request: {topic}\n"
        f"Findings so far: {_json(findings)}\n\n"
        "Return the recorded research decision."
    )


async def _plan_next_research_phase(
    topic: str,
    completed: set[str],
    findings: dict[str, Any],
) -> str:
    result = await agent_runner(
        starting_agent=research_planner,
        input=_research_phase_prompt(topic, completed, findings),
    )
    return choose_guarded_research_action(
        extract_research_action(str(result.final_output)),
        completed,
    )


def _run_research_phase(
    action: str,
    topic: str,
    findings: dict[str, Any],
) -> Any:
    if action == "public_sources":
        return _search_public_sources_step(topic)
    if action == "counterarguments":
        return _gather_counterarguments_step(topic)
    if action == "evidence_brief":
        return _assemble_evidence_brief_step(
            _json(findings["public_sources"]),
            _json(findings["counterarguments"]),
        )
    raise ValueError(f"Unknown research phase: {action}")


@register_agent(name="research-handoff-agent")
async def run_agent(message: str) -> str:
    completed: set[str] = set()
    findings: dict[str, Any] = {}

    for _ in range(MAX_RESEARCH_DECISIONS):
        next_action = await _plan_next_research_phase(message, completed, findings)
        if next_action == "final":
            break

        logger.info("research-handoff-agent selected phase: %s", next_action)
        findings[next_action] = _run_research_phase(next_action, message, findings)
        completed.add(next_action)

        if len(completed) == len(REQUIRED_RESEARCH_PHASES):
            break

    missing = [phase for phase in REQUIRED_RESEARCH_PHASES if phase not in completed]
    for phase in missing:
        logger.info("research-handoff-agent guardrail selected missing phase: %s", phase)
        findings[phase] = _run_research_phase(phase, message, findings)
        completed.add(phase)

    result = await agent_runner(
        starting_agent=synthesis_writer,
        input=(
            "Write the final research memo from this completed queued research "
            f"workflow.\n\nOriginal request:\n{message}\n\n"
            f"Completed findings:\n{_json(findings)}"
        ),
    )
    final_output = str(result.final_output)
    logger.info("research-handoff-agent final output:\n%s", final_output)
    print(f"research-handoff-agent final output:\n{final_output}")
    return final_output
