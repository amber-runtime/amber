import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agents import Agent, function_tool
from dbos import DBOS

from sdk import agent_runner, logger, register_agent, step

QUOTE_CLOCK = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
MAX_SPECIALIST_STEPS = 4
REQUIRED_SPECIALISTS = ("account_context", "integration_risk", "rollout_plan")
FORCE_ENTERPRISE_BRANCH_DIRECTIVE = "[demo:force_enterprise_compliance]"
FAIL_COMPLIANCE_HANDOFF_DIRECTIVE = "[demo:fail_compliance_handoff]"
COMMIT_RECEIPT_DIR = Path("/tmp/amber-enterprise-onboarding-receipts")


def _stable_int(*parts: str, modulo: int = 1000) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def _json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _timestamps() -> tuple[str, str]:
    created_at = QUOTE_CLOCK.isoformat().replace("+00:00", "Z")
    expires_at = (QUOTE_CLOCK + timedelta(hours=8)).isoformat().replace("+00:00", "Z")
    return created_at, expires_at


def _workflow_file_key(workflow_id: str) -> str:
    return workflow_id.replace("/", "_")


def enable_enterprise_compliance_branch(request: str) -> str:
    return f"{request}\n\n{FORCE_ENTERPRISE_BRANCH_DIRECTIVE}"


def enable_compliance_handoff_failure(request: str) -> str:
    return f"{request}\n\n{FAIL_COMPLIANCE_HANDOFF_DIRECTIVE}"


def enable_enterprise_failure_demo(request: str) -> str:
    return enable_compliance_handoff_failure(enable_enterprise_compliance_branch(request))


def _strip_directive(request: str, directive: str) -> tuple[str, bool]:
    if directive not in request:
        return request, False
    return request.replace(directive, "").strip(), True


def _extract_demo_directives(request: str) -> tuple[str, bool, bool]:
    request, force_branch = _strip_directive(request, FORCE_ENTERPRISE_BRANCH_DIRECTIVE)
    request, fail_handoff = _strip_directive(request, FAIL_COMPLIANCE_HANDOFF_DIRECTIVE)
    return request, force_branch, fail_handoff


def _parse_company_name(request: str) -> str:
    patterns = [
        r"\bfor\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\s+with|\s+across|\s+in|\s+onboarding|\.)",
        r"\baccount\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\s+with|\s+across|\s+in|\.)",
        r"\bcustomer\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\s+with|\s+across|\s+in|\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, request)
        if match:
            company = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;")
            if company:
                return company
    return "Northstar Health"


def _detect_industry(request: str) -> str:
    lowered = request.lower()
    if any(word in lowered for word in ("health", "hospital", "payer", "hipaa")):
        return "healthcare"
    if any(word in lowered for word in ("bank", "fintech", "sox", "pci", "finance")):
        return "financial_services"
    if any(word in lowered for word in ("public sector", "government", "federal")):
        return "public_sector"
    return "software"


def _detect_regions(request: str) -> list[str]:
    lowered = request.lower()
    regions = []
    if "us" in lowered or "united states" in lowered or "north america" in lowered:
        regions.append("us")
    if "eu" in lowered or "europe" in lowered or "emea" in lowered:
        regions.append("eu")
    if "uk" in lowered or "united kingdom" in lowered:
        regions.append("uk")
    if "apac" in lowered or "asia" in lowered:
        regions.append("apac")
    return regions or ["us"]


def _detect_seat_count(request: str) -> int:
    match = re.search(r"\b(\d{3,5})\s+(?:seats|users|employees)\b", request, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 1800 if "enterprise" in request.lower() else 220


def _detect_security_review(request: str) -> str:
    lowered = request.lower()
    if any(word in lowered for word in ("hipaa", "pci", "sox", "regulated", "security review")):
        return "enhanced"
    return "standard"


@step()
def normalize_onboarding_request(request: str) -> dict[str, Any]:
    """Turn a loose onboarding request into deterministic structured account data."""
    account_name = _parse_company_name(request)
    industry = _detect_industry(request)
    regions = _detect_regions(request)
    seat_count = _detect_seat_count(request)
    requires_procurement = bool(re.search(r"\bprocurement|msa|legal review|vendor review\b", request, re.IGNORECASE))
    requires_regional_controls = len(regions) > 1
    is_enterprise = seat_count >= 1000 or "enterprise" in request.lower()
    return {
        "account_name": account_name,
        "account_id": f"acct-{_stable_int(account_name, modulo=99999):05d}",
        "industry": industry,
        "seat_count": seat_count,
        "deployment_regions": regions,
        "owner_email": "ae@amber-demo.example",
        "launch_window": "2026-Q3",
        "system_of_record": "Salesforce",
        "security_review": _detect_security_review(request),
        "requires_procurement": requires_procurement,
        "requires_regional_controls": requires_regional_controls,
        "is_enterprise": is_enterprise,
        "original_request": request,
    }


@step()
def determine_workflow_branch(account: dict[str, Any], *, force_enterprise_branch: bool = False) -> str:
    signals = [
        force_enterprise_branch,
        bool(account.get("is_enterprise")),
        bool(account.get("requires_procurement")),
        bool(account.get("requires_regional_controls")),
        account.get("industry") in {"healthcare", "financial_services", "public_sector"},
    ]
    return "enterprise_compliance" if any(signals) else "standard_onboarding"


@function_tool
@step()
def record_specialist_decision(next_action: str, rationale: str) -> str:
    return _json({"next_action": next_action, "rationale": rationale})


@function_tool
@step()
def gather_account_context(
    account_name: str,
    industry: str,
    seat_count: int,
    deployment_regions: list[str],
) -> str:
    created_at, expires_at = _timestamps()
    return _json(
        {
            "account_name": account_name,
            "industry": industry,
            "seat_count": seat_count,
            "deployment_regions": deployment_regions,
            "decision_window": "45_days",
            "exec_sponsor": "VP Operations",
            "success_metric": "time-to-first-production-agent",
            "captured_at": created_at,
            "refresh_by": expires_at,
        }
    )


@function_tool
@step()
def assess_integration_risk(
    system_of_record: str,
    security_review: str,
    deployment_regions: list[str],
) -> str:
    created_at, expires_at = _timestamps()
    risk_score = 22 + _stable_int(system_of_record, security_review, ",".join(deployment_regions), modulo=45)
    return _json(
        {
            "system_of_record": system_of_record,
            "security_review": security_review,
            "deployment_regions": deployment_regions,
            "risk_score": risk_score,
            "recommended_controls": [
                "sandbox validation",
                "workflow trace review",
                "human approval on external mutations",
            ],
            "captured_at": created_at,
            "refresh_by": expires_at,
        }
    )


@function_tool
@step()
def draft_rollout_plan(
    account_name: str,
    seat_count: int,
    launch_window: str,
    requires_procurement: bool,
) -> str:
    created_at, expires_at = _timestamps()
    wave_count = 3 if seat_count >= 1000 else 2
    return _json(
        {
            "account_name": account_name,
            "launch_window": launch_window,
            "wave_count": wave_count,
            "requires_procurement": requires_procurement,
            "milestones": [
                "sandbox validation",
                "pilot users enabled",
                "production handoff",
            ],
            "captured_at": created_at,
            "refresh_by": expires_at,
        }
    )


@step()
def stage_mutation_payloads(
    account: dict[str, Any],
    findings: dict[str, str],
    workflow_branch: str,
) -> dict[str, Any]:
    created_at, expires_at = _timestamps()
    return {
        "crm_update": {
            "account_id": account["account_id"],
            "lifecycle_stage": "implementation_review",
            "owner_email": account["owner_email"],
            "branch": workflow_branch,
            "updated_at": created_at,
        },
        "approval_email": {
            "to": "implementation-approvals@amber-demo.example",
            "subject": f"{account['account_name']} onboarding approval package",
            "highlights": [
                "multi-agent onboarding workflow completed",
                "side effects staged but not committed",
                f"branch={workflow_branch}",
            ],
            "expires_at": expires_at,
        },
        "compliance_ticket": {
            "ticket_id": f"cmp-{_stable_int(account['account_id'], workflow_branch, modulo=99999):05d}",
            "account_id": account["account_id"],
            "account_name": account["account_name"],
            "branch": workflow_branch,
            "required_controls": [
                "trace-reviewed replay path",
                "procurement artifacts attached",
                "human approval before external writes",
            ],
            "specialist_findings": findings,
            "created_at": created_at,
        },
    }


def _commit_receipt_path(workflow_id: str) -> Path:
    return COMMIT_RECEIPT_DIR / f"{_workflow_file_key(workflow_id)}.json"


@function_tool(failure_error_function=None)
@step()
def commit_compliance_handoff(ticket_payload: str, fail_handoff: bool = False) -> str:
    payload = json.loads(ticket_payload)
    if fail_handoff:
        logger.error(
            "Fatal demo failure while committing compliance handoff for account_id=%s",
            payload.get("account_id"),
        )
        raise RuntimeError("Compliance ticket schema mismatch blocked external handoff.")

    workflow_id = DBOS.workflow_id or "unknown-workflow"
    COMMIT_RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    receipt_path = _commit_receipt_path(workflow_id)
    receipt = {
        "workflow_id": workflow_id,
        "ticket_id": payload.get("ticket_id"),
        "account_id": payload.get("account_id"),
        "committed_at": _timestamps()[0],
        "status": "submitted",
    }
    receipt_path.write_text(_json(receipt), encoding="utf-8")
    return _json(receipt)


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


def extract_specialist_action(planner_output: str) -> str:
    decision = _parse_json_object(planner_output)
    action = str(decision.get("next_action", "")).strip()
    if action:
        return action

    match = re.search(
        r"\b(account_context|integration_risk|rollout_plan|final)\b",
        planner_output,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def choose_guarded_specialist_action(raw_action: str, completed: set[str]) -> str:
    action = raw_action.strip().lower()
    aliases = {
        "account": "account_context",
        "context": "account_context",
        "risk": "integration_risk",
        "integration": "integration_risk",
        "rollout": "rollout_plan",
        "plan": "rollout_plan",
        "done": "final",
        "finish": "final",
    }
    action = aliases.get(action, action)

    if action == "final":
        return "final" if len(completed) == len(REQUIRED_SPECIALISTS) else _first_missing_specialist(completed)
    if action not in REQUIRED_SPECIALISTS:
        return _first_missing_specialist(completed)
    if action in completed:
        return _first_missing_specialist(completed)
    return action


def _first_missing_specialist(completed: set[str]) -> str:
    for specialist in REQUIRED_SPECIALISTS:
        if specialist not in completed:
            return specialist
    return "final"


specialist_planner = Agent(
    name="enterprise_onboarding_planner",
    instructions=(
        "You are the onboarding workflow planner. Choose exactly one next action from "
        "account_context, integration_risk, rollout_plan, or final. Use "
        "record_specialist_decision exactly once. Do not choose final until all "
        "specialists are complete."
    ),
    tools=[record_specialist_decision],
)

account_context_researcher = Agent(
    name="account_context_researcher",
    instructions=(
        "Use gather_account_context exactly once. Return the account profile, decision "
        "window, and success metric."
    ),
    tools=[gather_account_context],
)

integration_risk_analyst = Agent(
    name="integration_risk_analyst",
    instructions=(
        "Use assess_integration_risk exactly once. Return the risk score and recommended controls."
    ),
    tools=[assess_integration_risk],
)

rollout_planner = Agent(
    name="rollout_planner",
    instructions=(
        "Use draft_rollout_plan exactly once. Return the rollout waves, milestones, and any gating items."
    ),
    tools=[draft_rollout_plan],
)

compliance_operator = Agent(
    name="compliance_operator",
    instructions=(
        "Use commit_compliance_handoff exactly once. This is a fatal external handoff "
        "boundary, not a best-effort tool. Return the commit receipt when successful."
    ),
    tools=[commit_compliance_handoff],
)

final_coordinator = Agent(
    name="enterprise_onboarding_coordinator",
    instructions=(
        "Synthesize the completed onboarding workflow into an operator-facing summary. "
        "Call out the selected branch, specialist outputs, staged side effects, and "
        "final compliance handoff status."
    ),
)

SPECIALIST_AGENTS = {
    "account_context": account_context_researcher,
    "integration_risk": integration_risk_analyst,
    "rollout_plan": rollout_planner,
}


def _specialist_prompt(action: str, account: dict[str, Any], findings: dict[str, str]) -> str:
    common = f"Normalized account:\n{_json(account)}"
    if action == "account_context":
        return (
            f"{common}\n\nCall gather_account_context exactly once using account_name, "
            "industry, seat_count, and deployment_regions."
        )
    if action == "integration_risk":
        return (
            f"{common}\n\nCall assess_integration_risk exactly once using system_of_record, "
            "security_review, and deployment_regions."
        )
    return (
        f"{common}\n\nFindings so far:\n{_json(findings)}\n\n"
        "Call draft_rollout_plan exactly once using account_name, seat_count, "
        "launch_window, and requires_procurement."
    )


async def _plan_next_specialist(account: dict[str, Any], completed: set[str], findings: dict[str, str]) -> str:
    result = await agent_runner(
        starting_agent=specialist_planner,
        input=(
            "Choose the next specialist for this enterprise onboarding workflow.\n\n"
            f"Required specialists: {', '.join(REQUIRED_SPECIALISTS)}\n"
            f"Completed specialists: {', '.join(sorted(completed)) or 'none'}\n"
            f"Normalized account: {_json(account)}\n"
            f"Findings so far: {_json(findings)}\n\n"
            "Return the recorded specialist decision."
        ),
    )
    return choose_guarded_specialist_action(
        extract_specialist_action(str(result.final_output)),
        completed,
    )


async def _run_specialists(account: dict[str, Any]) -> dict[str, str]:
    completed: set[str] = set()
    findings: dict[str, str] = {}

    for _ in range(MAX_SPECIALIST_STEPS):
        next_action = await _plan_next_specialist(account, completed, findings)
        if next_action == "final":
            break

        logger.info("enterprise-onboarding-error-demo selected specialist: %s", next_action)
        specialist_result = await agent_runner(
            starting_agent=SPECIALIST_AGENTS[next_action],
            input=_specialist_prompt(next_action, account, findings),
        )
        findings[next_action] = str(specialist_result.final_output)
        completed.add(next_action)

        if len(completed) == len(REQUIRED_SPECIALISTS):
            break

    missing = [name for name in REQUIRED_SPECIALISTS if name not in completed]
    for action in missing:
        logger.info("enterprise-onboarding-error-demo guardrail selected specialist: %s", action)
        specialist_result = await agent_runner(
            starting_agent=SPECIALIST_AGENTS[action],
            input=_specialist_prompt(action, account, findings),
        )
        findings[action] = str(specialist_result.final_output)
        completed.add(action)

    return findings


@register_agent(name="enterprise-onboarding-error-demo")
async def enterprise_onboarding_error_demo(request: str) -> str:
    request, force_enterprise_branch, fail_compliance_handoff = _extract_demo_directives(request)
    account = normalize_onboarding_request(request)
    workflow_branch = determine_workflow_branch(
        account,
        force_enterprise_branch=force_enterprise_branch,
    )
    findings = await _run_specialists(account)
    staged_payloads = stage_mutation_payloads(account, findings, workflow_branch)
    branch_signals = {
        "enterprise": bool(account.get("is_enterprise")),
        "regulated": account.get("industry") in {"healthcare", "financial_services", "public_sector"},
        "procurement": bool(account.get("requires_procurement")),
    }

    compliance_result = "Not required for standard onboarding."
    if workflow_branch == "enterprise_compliance":
        logger.info("enterprise-onboarding-error-demo entering rare branch: %s", workflow_branch)
        compliance_agent_result = await agent_runner(
            starting_agent=compliance_operator,
            input=(
                "Commit the enterprise compliance handoff for this exact workflow state.\n\n"
                f"Signals: {_json(branch_signals)}\n"
                f"Staged payloads:\n{_json(staged_payloads)}\n\n"
                "Call commit_compliance_handoff exactly once using the compliance_ticket "
                f"payload and fail_handoff={str(fail_compliance_handoff)}."
            ),
        )
        compliance_result = str(compliance_agent_result.final_output)

    result = await agent_runner(
        starting_agent=final_coordinator,
        input=(
            "Create the final onboarding summary from this deterministic workflow.\n\n"
            f"Workflow branch: {workflow_branch}\n\n"
            f"Normalized account:\n{_json(account)}\n\n"
            f"Specialist findings:\n{_json(findings)}\n\n"
            f"Staged payloads:\n{_json(staged_payloads)}\n\n"
            f"Compliance handoff result:\n{compliance_result}"
        ),
    )
    final_output = str(result.final_output)
    logger.info("enterprise-onboarding-error-demo final output:\n%s", final_output)
    print(f"enterprise-onboarding-error-demo final output:\n{final_output}")
    return final_output
