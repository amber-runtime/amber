import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import Agent, function_tool
from ddgs import DDGS

from sdk import agent_runner, current_workflow_id, logger, register_agent, step

BRIEF_CLOCK = datetime(2026, 6, 4, 9, 0, tzinfo=timezone.utc)
MAX_RESEARCH_STEPS = 5
REQUIRED_RESEARCH_MODULES = (
    "news_research",
    "market_positioning",
    "tech_stack_signals",
)

ENTERPRISE_BRANCH_DIRECTIVE = "[demo:enterprise_account]"
TRIGGER_RATELIMIT_DIRECTIVE = "[demo:trigger_ratelimit]"

_RATELIMIT_THRESHOLD_SECONDS = 1.0
_ratelimit_workflows: set[str] = set()

OUTREACH_RECEIPT_DIR = Path("/tmp/amber-account-research-outreach-receipts")

SAMPLE_INPUT = (
    "Research Meridian Logistics before our enterprise call next week. "
    "They're evaluating us against two incumbents and we need recent news, "
    "their tech stack, and pricing signals before we can position correctly."
)


class DeepScanThrottleError(ConnectionError):
    pass


def _stable_int(*parts: str, modulo: int = 1000) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def _json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _brief_timestamp() -> str:
    return BRIEF_CLOCK.isoformat().replace("+00:00", "Z")


def _workflow_file_key(workflow_id: str) -> str:
    return workflow_id.replace("/", "_")


def enable_enterprise_account(request: str) -> str:
    return f"{request}\n\n{ENTERPRISE_BRANCH_DIRECTIVE}"


def enable_ratelimit_trigger(request: str) -> str:
    return f"{request}\n\n{TRIGGER_RATELIMIT_DIRECTIVE}"


def enable_account_research_failure_demo(request: str) -> str:
    return enable_ratelimit_trigger(enable_enterprise_account(request))


def _strip_directive(request: str, directive: str) -> tuple[str, bool]:
    if directive not in request:
        return request, False
    return request.replace(directive, "").strip(), True


def _extract_demo_directives(request: str) -> tuple[str, bool, bool]:
    request, is_enterprise = _strip_directive(request, ENTERPRISE_BRANCH_DIRECTIVE)
    request, trigger_ratelimit = _strip_directive(request, TRIGGER_RATELIMIT_DIRECTIVE)
    return request, is_enterprise, trigger_ratelimit


def _parse_company_name(request: str) -> str:
    patterns = [
        r"\bResearch\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:\s+before|\s+for|\s+on|,|\.)",
        r"\bfor\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\s+before|\s+against|\s+vs|\s+on|\s+in|\.)",
        r"\babout\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\s+before|\s+against|\s+vs|\s+on|\s+in|\.)",
        r"\bon\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\s+before|\s+against|\s+vs|\s+in|\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, request)
        if match:
            company = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;")
            if company:
                return company
    return "Meridian Logistics"


def _detect_industry(request: str) -> str:
    lowered = request.lower()
    if any(
        w in lowered
        for w in ("logistics", "freight", "supply chain", "shipping", "transport")
    ):
        return "logistics"
    if any(w in lowered for w in ("health", "hospital", "payer", "pharma", "hipaa")):
        return "healthcare"
    if any(
        w in lowered for w in ("bank", "fintech", "finance", "insurance", "pci", "sox")
    ):
        return "financial_services"
    if any(w in lowered for w in ("retail", "ecommerce", "e-commerce", "consumer")):
        return "retail"
    return "software"


def _detect_incumbent_count(request: str) -> int:
    match = re.search(r"\b(\w+)\s+incumbent", request, re.IGNORECASE)
    if match:
        mapping = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        return mapping.get(match.group(1).lower(), 2)
    match = re.search(r"\b(\d)\s+incumbent", request, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 1


def _detect_ae_email(request: str) -> str:
    match = re.search(
        r"\b([a-z][a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})\b",
        request,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return "ae@amber-demo.example"


@step(name="normalize_account_request")
def normalize_account_request(request: str) -> dict[str, Any]:
    company = _parse_company_name(request)
    industry = _detect_industry(request)
    incumbent_count = _detect_incumbent_count(request)
    ae_email = _detect_ae_email(request)
    is_enterprise = (
        incumbent_count >= 2
        or "enterprise" in request.lower()
        or industry in {"healthcare", "financial_services"}
    )
    return {
        "company": company,
        "company_id": f"acct-{_stable_int(company, modulo=99999):05d}",
        "industry": industry,
        "incumbent_count": incumbent_count,
        "is_enterprise": is_enterprise,
        "ae_email": ae_email,
        "brief_requested_at": _brief_timestamp(),
        "original_request": request,
    }


@step(name="determine_workflow_branch")
def determine_workflow_branch(
    account: dict[str, Any],
    *,
    force_enterprise_branch: bool = False,
) -> str:
    if force_enterprise_branch or account.get("is_enterprise"):
        return "enterprise"
    return "standard"


@step(name="stage_outreach_payloads")
def stage_outreach_payloads(
    account: dict[str, Any],
    findings: dict[str, str],
) -> dict[str, Any]:
    return {
        "email_payload": {
            "to": account["ae_email"],
            "subject": f"Pre-call Research Brief: {account['company']}",
            "research_modules": list(findings.keys()),
            "prepared_at": _brief_timestamp(),
        },
        "crm_activity": {
            "company_id": account["company_id"],
            "activity_type": "pre_call_research_brief",
            "incumbent_count": account["incumbent_count"],
            "prepared_at": _brief_timestamp(),
        },
    }


@function_tool
@step(name="record_research_decision")
def record_research_decision(next_action: str, rationale: str) -> str:
    return _json({"next_action": next_action, "rationale": rationale})


@function_tool
@step(name="lookup_crm_account")
def lookup_crm_account(company: str, industry: str) -> str:
    employee_count = 300 + _stable_int(company, "headcount", modulo=4700)
    arr_estimate = 500_000 + _stable_int(company, "arr", modulo=9_500_000)
    return _json(
        {
            "company": company,
            "industry": industry,
            "employee_count": employee_count,
            "estimated_arr_usd": arr_estimate,
            "crm_stage": "active_opportunity",
            "last_touch_date": "2026-05-12",
            "primary_contact": f"VP Operations — {company}",
            "source": "salesforce_cache",
        }
    )


@function_tool
@step(name="fetch_pricing_signals")
def fetch_pricing_signals(company: str, incumbent_count: int) -> str:
    base_acv = 42_000 + _stable_int(company, "acv", modulo=78_000)
    discount_pct = 5 + _stable_int(company, "discount", modulo=18)
    return _json(
        {
            "company": company,
            "estimated_acv_usd": base_acv,
            "typical_discount_pct": discount_pct,
            "competitor_price_range": f"${base_acv - 10_000:,}–${base_acv + 20_000:,}",
            "incumbent_count": incumbent_count,
            "price_sensitivity": "high" if incumbent_count >= 2 else "medium",
            "source": "deal_desk_cache",
        }
    )


@function_tool
@step(name="get_known_tech_stack")
def get_known_tech_stack(company: str, industry: str) -> str:
    stacks: dict[str, list[str]] = {
        "logistics": ["SAP TM", "Oracle WMS", "Salesforce", "Snowflake"],
        "healthcare": ["Epic", "Salesforce Health Cloud", "AWS", "Tableau"],
        "financial_services": ["Workday", "Salesforce", "Azure", "dbt"],
        "retail": ["Shopify", "NetSuite", "Google Cloud", "Looker"],
        "software": ["Salesforce", "AWS", "Postgres", "dbt"],
    }
    tools = stacks.get(industry, stacks["software"])
    seed = _stable_int(company, industry, modulo=len(tools))
    rotated = tools[seed:] + tools[:seed]
    return _json(
        {
            "company": company,
            "known_tools": rotated,
            "api_maturity": "high" if seed > 1 else "medium",
            "cloud_provider": rotated[-1] if rotated else "unknown",
            "source": "enrichment_db",
        }
    )


@function_tool
@step(name="search_recent_news")
def search_recent_news(company: str, industry: str) -> str:
    query = f"{company} {industry} news 2026"
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=4))
    if not results:
        return _json({"company": company, "articles": [], "query": query})
    articles = [
        {"title": r["title"], "url": r["href"], "snippet": r["body"][:200]}
        for r in results
    ]
    return _json({"company": company, "query": query, "articles": articles})


@function_tool
@step(name="search_competitor_positioning")
def search_competitor_positioning(company: str, industry: str) -> str:
    query = f"{company} alternatives competitors {industry} 2026"
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=4))
    if not results:
        return _json({"company": company, "positioning": [], "query": query})
    positioning = [
        {"title": r["title"], "url": r["href"], "snippet": r["body"][:200]}
        for r in results
    ]
    return _json({"company": company, "query": query, "positioning": positioning})


@function_tool
@step(name="search_hiring_signals")
def search_hiring_signals(company: str) -> str:
    query = f"{company} jobs hiring 2026 site:linkedin.com OR site:greenhouse.io"
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=3))
    if not results:
        return _json({"company": company, "signals": [], "query": query})
    signals = [{"role": r["title"], "snippet": r["body"][:150]} for r in results]
    return _json({"company": company, "query": query, "hiring_signals": signals})


_DEEP_SCAN_QUERIES = [
    "{company} market share competitive landscape {industry}",
    "{company} customer case study win loss review",
    "{company} pricing model enterprise contract structure",
    "{company} technology integration partner ecosystem",
    "{company} executive leadership strategic initiative growth",
]


@function_tool(failure_error_function=None)
@step(name="scrape_deep_competitive_signals")
def scrape_deep_competitive_signals(company: str, industry: str) -> str:
    workflow_id = current_workflow_id()
    signals: list[dict[str, Any]] = []
    last_query_time = time.monotonic()

    for i, query_template in enumerate(_DEEP_SCAN_QUERIES, start=1):
        query = query_template.format(company=company, industry=industry)
        # DEMO FORK 2: Uncomment the next line to add backoff so the deep scan succeeds.
        time.sleep(1.5)

        elapsed = time.monotonic() - last_query_time

        # DEMO FORK 1: Uncomment the next line to reveal the real failure cause in logs.
        if i == 3 and elapsed < _RATELIMIT_THRESHOLD_SECONDS:
            logger.warning(
                "DuckDuckGo deep scan throttled on query %d/%d for %s: %.2fs since last search is below the %.2fs safety threshold; likely scraper rate limit",
                i,
                len(_DEEP_SCAN_QUERIES),
                company,
                elapsed,
                _RATELIMIT_THRESHOLD_SECONDS,
            )

        if (
            workflow_id in _ratelimit_workflows
            and i == 3
            and elapsed < _RATELIMIT_THRESHOLD_SECONDS
        ):
            raise DeepScanThrottleError("Remote end closed connection without response")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))

        last_query_time = time.monotonic()
        signals.append(
            {
                "query_index": i,
                "query": query,
                "result_count": len(results),
                "top_result": results[0]["body"][:250] if results else None,
            }
        )

    return _json(
        {
            "company": company,
            "industry": industry,
            "query_count": len(_DEEP_SCAN_QUERIES),
            "signals": signals,
            "source": "ddgs_deep_scan",
        }
    )


@function_tool(failure_error_function=None)
@step(name="send_account_brief_email")
def send_account_brief_email(
    ae_email: str,
    company: str,
    brief_summary: str,
) -> str:
    workflow_id = current_workflow_id() or "unknown-workflow"
    OUTREACH_RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    receipt_path = OUTREACH_RECEIPT_DIR / f"{_workflow_file_key(workflow_id)}.json"
    receipt = {
        "workflow_id": workflow_id,
        "to": ae_email,
        "subject": f"Pre-call Research Brief: {company}",
        "status": "sent",
        "sent_at": _brief_timestamp(),
        "brief_excerpt": brief_summary[:500],
    }
    receipt_path.write_text(_json(receipt), encoding="utf-8")
    logger.info(
        "account-research-error-demo brief email sent to %s for company=%s",
        ae_email,
        company,
    )
    return _json(receipt)


research_planner = Agent(
    name="account_research_planner",
    instructions=(
        "You are the account research workflow planner. Choose exactly one next action "
        "from: news_research, market_positioning, tech_stack_signals, or final. Use "
        "record_research_decision exactly once. Do not choose final until all three "
        "research modules are complete."
    ),
    tools=[record_research_decision],
)

news_researcher = Agent(
    name="news_researcher",
    instructions=(
        "Use search_recent_news exactly once. Return a concise summary of recent news "
        "signals: fundraising, leadership changes, product launches, or market moves."
    ),
    tools=[search_recent_news],
)

market_positioning_analyst = Agent(
    name="market_positioning_analyst",
    instructions=(
        "Use lookup_crm_account, then fetch_pricing_signals, then "
        "search_competitor_positioning. Return the CRM profile, pricing context, "
        "and how competitors are positioned for this account."
    ),
    tools=[lookup_crm_account, fetch_pricing_signals, search_competitor_positioning],
)

tech_stack_analyst = Agent(
    name="tech_stack_analyst",
    instructions=(
        "Use get_known_tech_stack and search_hiring_signals exactly once each. Return "
        "the known tech stack, integration surface, and hiring signals that reveal "
        "strategic direction."
    ),
    tools=[get_known_tech_stack, search_hiring_signals],
)

brief_compiler = Agent(
    name="brief_compiler",
    instructions=(
        "Synthesize completed research module findings into a structured pre-call brief "
        "with: executive summary, competitive landscape, pricing context, tech stack, "
        "and recommended positioning approach for the AE."
    ),
)

outreach_operator = Agent(
    name="outreach_operator",
    instructions=(
        "Use send_account_brief_email exactly once. This is an irreversible external "
        "side effect — sending the research brief to the AE. Return the send receipt."
    ),
    tools=[send_account_brief_email],
)

deep_scan_agent = Agent(
    name="deep_scan_agent",
    instructions=(
        "Use scrape_deep_competitive_signals exactly once using company and industry. "
        "This is a deep five-query competitive scan for enterprise accounts. "
        "Return the full signal pack."
    ),
    tools=[scrape_deep_competitive_signals],
)

research_coordinator = Agent(
    name="research_coordinator",
    instructions=(
        "Synthesize the completed account research workflow into a final operator-facing "
        "summary. Call out which research modules ran, the brief send status, "
        "and the deep scan findings (if the enterprise branch was taken)."
    ),
)

RESEARCH_MODULE_AGENTS: dict[str, Agent] = {
    "news_research": news_researcher,
    "market_positioning": market_positioning_analyst,
    "tech_stack_signals": tech_stack_analyst,
}


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
        r"\b(news_research|news|market_positioning|positioning|market|"
        r"tech_stack_signals|tech_stack|tech|final)\b",
        planner_output,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _first_missing_module(completed: set[str]) -> str:
    for module in REQUIRED_RESEARCH_MODULES:
        if module not in completed:
            return module
    return "final"


def choose_guarded_module_action(raw_action: str, completed: set[str]) -> str:
    action = raw_action.strip().lower()
    aliases = {
        "news": "news_research",
        "news_research": "news_research",
        "market": "market_positioning",
        "positioning": "market_positioning",
        "market_positioning": "market_positioning",
        "tech": "tech_stack_signals",
        "tech_stack": "tech_stack_signals",
        "tech_stack_signals": "tech_stack_signals",
        "done": "final",
        "finish": "final",
    }
    action = aliases.get(action, action)

    if action == "final":
        return (
            "final"
            if len(completed) == len(REQUIRED_RESEARCH_MODULES)
            else _first_missing_module(completed)
        )
    if action not in REQUIRED_RESEARCH_MODULES:
        return _first_missing_module(completed)
    if action in completed:
        return _first_missing_module(completed)
    return action


def _module_prompt(
    action: str, account: dict[str, Any], findings: dict[str, str]
) -> str:
    common = f"Account:\n{_json(account)}"
    if action == "news_research":
        return (
            f"{common}\n\nCall search_recent_news exactly once using "
            f"company={account['company']!r} and industry={account['industry']!r}."
        )
    if action == "market_positioning":
        return (
            f"{common}\n\nCall lookup_crm_account using company and industry. "
            f"Then call fetch_pricing_signals using company and "
            f"incumbent_count={account['incumbent_count']}. "
            "Then call search_competitor_positioning using company and industry. "
            "Return the combined pricing and positioning picture."
        )
    return (
        f"{common}\n\nCall get_known_tech_stack using company and industry. "
        "Then call search_hiring_signals using company. Synthesize tech profile."
    )


async def _plan_next_module(
    account: dict[str, Any],
    completed: set[str],
    findings: dict[str, str],
) -> str:
    result = await agent_runner(
        starting_agent=research_planner,
        input=(
            "Choose the next research module for this account research workflow.\n\n"
            f"Required modules: {', '.join(REQUIRED_RESEARCH_MODULES)}\n"
            f"Completed modules: {', '.join(sorted(completed)) or 'none'}\n"
            f"Account: {_json(account)}\n"
            f"Findings so far: {_json(findings)}\n\n"
            "Return the recorded research decision."
        ),
    )
    return choose_guarded_module_action(
        extract_research_action(str(result.final_output)),
        completed,
    )


async def _run_standard_research(account: dict[str, Any]) -> dict[str, str]:
    completed: set[str] = set()
    findings: dict[str, str] = {}

    for _ in range(MAX_RESEARCH_STEPS):
        next_action = await _plan_next_module(account, completed, findings)
        if next_action == "final":
            break

        logger.info("account-research-error-demo selected module: %s", next_action)
        module_result = await agent_runner(
            starting_agent=RESEARCH_MODULE_AGENTS[next_action],
            input=_module_prompt(next_action, account, findings),
        )
        findings[next_action] = str(module_result.final_output)
        completed.add(next_action)

        if len(completed) == len(REQUIRED_RESEARCH_MODULES):
            break

    missing = [m for m in REQUIRED_RESEARCH_MODULES if m not in completed]
    for action in missing:
        logger.info("account-research-error-demo guardrail selected module: %s", action)
        module_result = await agent_runner(
            starting_agent=RESEARCH_MODULE_AGENTS[action],
            input=_module_prompt(action, account, findings),
        )
        findings[action] = str(module_result.final_output)
        completed.add(action)

    return findings


@register_agent(name="account-research-error-demo")
async def account_research_error_demo(request: str) -> str:
    request, is_enterprise, trigger_ratelimit = _extract_demo_directives(request)

    workflow_id = current_workflow_id()
    if trigger_ratelimit and workflow_id:
        _ratelimit_workflows.add(workflow_id)

    account = normalize_account_request(request)
    workflow_branch = determine_workflow_branch(
        account,
        force_enterprise_branch=is_enterprise,
    )
    findings = await _run_standard_research(account)
    staged_payloads = stage_outreach_payloads(account, findings)

    brief_result = await agent_runner(
        starting_agent=brief_compiler,
        input=(
            "Compile a pre-call research brief from the completed standard research.\n\n"
            f"Account:\n{_json(account)}\n\n"
            f"Research findings:\n{_json(findings)}"
        ),
    )
    compiled_brief = str(brief_result.final_output)

    outreach_result = await agent_runner(
        starting_agent=outreach_operator,
        input=(
            "Send the pre-call research brief to the AE. "
            "This is an irreversible external side effect.\n\n"
            f"AE email: {account['ae_email']}\n"
            f"Company: {account['company']}\n"
            f"Brief summary:\n{compiled_brief[:600]}"
        ),
    )

    deep_scan_result = "Not required for standard accounts."
    if workflow_branch == "enterprise":
        logger.info(
            "account-research-error-demo entering enterprise branch for company=%s",
            account["company"],
        )
        deep_result = await agent_runner(
            starting_agent=deep_scan_agent,
            input=(
                "Run the deep competitive scan for this enterprise account.\n\n"
                f"Company: {account['company']}\n"
                f"Industry: {account['industry']}\n\n"
                "Call scrape_deep_competitive_signals exactly once using company and industry."
            ),
        )
        deep_scan_result = str(deep_result.final_output)

    result = await agent_runner(
        starting_agent=research_coordinator,
        input=(
            "Produce the final operator-facing summary of this account research workflow.\n\n"
            f"Account:\n{_json(account)}\n"
            f"Workflow branch: {workflow_branch}\n\n"
            f"Standard research findings:\n{_json(findings)}\n\n"
            f"Staged payloads:\n{_json(staged_payloads)}\n\n"
            f"Email send result:\n{outreach_result.final_output}\n\n"
            f"Enterprise deep scan result:\n{deep_scan_result}"
        ),
    )
    final_output = str(result.final_output)
    logger.info("account-research-error-demo final output:\n%s", final_output)
    print(f"account-research-error-demo final output:\n{final_output}")
    return final_output
