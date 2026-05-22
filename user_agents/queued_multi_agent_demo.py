from __future__ import annotations

from typing import Any

from agents import Agent, function_tool, handoff

from sdk import register_agent, agentic_runner, logger, step

SAMPLE_MESSAGE = (
    "Prepare a deep research memo on whether midsize logistics operators should adopt "
    "AI dispatch copilots over the next 18 months. Gather source material, surface "
    "counterarguments, and end with a recommendation plus open risks."
)
HANDOFF_NOTE = (
    "DBOS durably stores workflow and step execution. The dashboard enriches that with "
    "agent events from the SDK. Handoff events are expected on successful queued runs."
)


@function_tool
@step()
def search_public_sources(topic: str) -> dict[str, Any]:
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
@step()
def gather_counterarguments(topic: str) -> dict[str, Any]:
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
@step()
def assemble_evidence_brief(public_pack: str, counterarguments: str) -> dict[str, Any]:
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


source_collector = Agent(
    name="source_collector",
    instructions=(
        "You are the source collection specialist for long-running deep research. "
        "Gather grounded evidence using the available tools, organize it for downstream "
        "agents, and clearly separate observed evidence from open questions."
    ),
    tools=[search_public_sources, gather_counterarguments],
)

synthesis_writer = Agent(
    name="synthesis_writer",
    instructions=(
        "You are the synthesis specialist. Build a crisp research memo that cites the "
        "evidence provided by prior agents, highlights disagreements, and ends with a "
        "decision-ready recommendation plus unresolved risks."
    ),
    tools=[assemble_evidence_brief],
)

research_coordinator = Agent(
    name="research_coordinator",
    instructions=(
        "You orchestrate durable deep research across specialist agents. First hand off "
        "to the source collector to gather evidence and counterarguments. Then hand off "
        "to the synthesis writer to produce the final memo. Do not answer directly until "
        "the specialist chain has completed."
    ),
    handoffs=[
        handoff(
            source_collector,
            tool_name_override="delegate_source_collection",
            tool_description_override=(
                "Hand off to the source collection specialist for evidence gathering."
            ),
        ),
        handoff(
            synthesis_writer,
            tool_name_override="delegate_synthesis",
            tool_description_override=(
                "Hand off to the synthesis specialist for memo writing."
            ),
        ),
    ],
)


@register_agent(name="research-handoff-agent")
async def run_agent(message: str) -> str:
    result = await agentic_runner(
        starting_agent=research_coordinator,
        input=message,
    )
    final_output = str(result.final_output)
    logger.info("research-handoff-agent final output:\n%s", final_output)
    print(f"research-handoff-agent final output:\n{final_output}")
    return final_output
