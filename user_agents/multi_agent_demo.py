import hashlib
import json
import os
import re
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agents import Agent, function_tool
from dbos import DBOS

from sdk import register_agent, agentic_runner, logger, step

QUOTE_CLOCK = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
REQUIRED_SPECIALISTS = ("flight", "hotel", "local", "budget")
MAX_COORDINATOR_DECISIONS = 6
SPECIALIST_AGENTS: dict[str, Agent] = {}
CRASH_DURING_HOTEL_DIRECTIVE = "[checkpoint:crash_during_hotel]"
CRASH_MARKER_DIR = Path("/tmp/dbos-travel-concierge-crashes")
CRASH_REQUEST_DIR = Path("/tmp/dbos-travel-concierge-crash-requests")


def _stable_int(*parts: str, modulo: int = 1000) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def _quote_times() -> tuple[str, str]:
    quoted_at = QUOTE_CLOCK.isoformat().replace("+00:00", "Z")
    expires_at = (QUOTE_CLOCK + timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    return quoted_at, expires_at


def _json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def request_hotel_crash_demo(request: str) -> str:
    return f"{request}\n\n{CRASH_DURING_HOTEL_DIRECTIVE}"


def _workflow_file_key(workflow_id: str) -> str:
    return workflow_id.replace("/", "_")


def _crash_request_path(workflow_id: str) -> Path:
    return CRASH_REQUEST_DIR / _workflow_file_key(workflow_id)


def _crash_marker_path(workflow_id: str) -> Path:
    return CRASH_MARKER_DIR / _workflow_file_key(workflow_id)


def _request_hotel_crash(workflow_id: str | None) -> None:
    if not workflow_id:
        return
    CRASH_REQUEST_DIR.mkdir(parents=True, exist_ok=True)
    _crash_request_path(workflow_id).write_text(
        "crash during hotel quotes\n",
        encoding="utf-8",
    )


def _crash_once_during_hotel(workflow_id: str | None) -> None:
    if not workflow_id:
        return

    request_path = _crash_request_path(workflow_id)
    if not request_path.exists():
        return

    marker_path = _crash_marker_path(workflow_id)
    if marker_path.exists():
        return

    CRASH_MARKER_DIR.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("crashed once during hotel quotes\n", encoding="utf-8")
    request_path.unlink(missing_ok=True)
    logger.warning("Intentional demo crash during get_hotel_quotes")
    os.kill(os.getpid(), signal.SIGTERM)


def _strip_hotel_crash_directive(request: str) -> tuple[str, bool]:
    if CRASH_DURING_HOTEL_DIRECTIVE not in request:
        return request, False
    cleaned = request.replace(CRASH_DURING_HOTEL_DIRECTIVE, "").strip()
    return cleaned, True


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


def extract_planner_action(planner_output: str) -> str:
    decision = _parse_json_object(planner_output)
    action = str(decision.get("next_action", "")).strip()
    if action:
        return action

    match = re.search(
        r"\b(flight|flights|hotel|hotels|local|activities|activity|budget|final|finish|done)\b",
        planner_output,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _first_missing_specialist(completed: set[str]) -> str:
    for specialist in REQUIRED_SPECIALISTS:
        if specialist not in completed:
            return specialist
    return "final"


def choose_guarded_next_action(raw_action: str, completed: set[str]) -> str:
    action = raw_action.strip().lower().replace("_reviewer", "").replace("_planner", "")
    aliases = {
        "flights": "flight",
        "flight_researcher": "flight",
        "hotels": "hotel",
        "hotel_researcher": "hotel",
        "activities": "local",
        "activity": "local",
        "local_planner": "local",
        "budget_reviewer": "budget",
        "budget_review": "budget",
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


def _format_place(place: str, *, uppercase_three_letter_code: bool = False) -> str:
    words = re.sub(r"\s+", " ", place.strip(" ,.;:!?")).split()
    if uppercase_three_letter_code and len(words) == 1 and re.fullmatch(r"[A-Za-z]{3}", words[0]):
        return words[0].upper()

    formatted = []
    for word in words:
        normalized = word.upper()
        if normalized in {"DC", "NYC", "LA", "SF"}:
            formatted.append(normalized)
        else:
            formatted.append(word[:1].upper() + word[1:].lower())
    return " ".join(formatted)


def _simple_origin(request: str) -> str | None:
    stop_words = (
        r"to|for|departing|returning|budget|under|around|with|on|between|"
        r"starting|leaving|arriving|in|by"
    )
    match = re.search(
        rf"\bfrom\s+([A-Za-z][A-Za-z\s]+?)(?:\s+(?:{stop_words})\b|,|\.|$)",
        request,
        re.IGNORECASE,
    )
    if not match:
        return None

    origin = _format_place(match.group(1), uppercase_three_letter_code=True)
    return origin or None


def _simple_destination(request: str) -> str:
    stop_words = (
        r"from|for|departing|returning|budget|under|around|with|on|between|"
        r"starting|leaving|arriving|in|by"
    )
    destination_patterns = [
        rf"\b(?:trip|travel|vacation|holiday|journey|flight|flights)\s+to\s+"
        rf"([A-Za-z][A-Za-z\s]+?)(?:\s+(?:{stop_words})\b|,|\.|$)",
        rf"\b(?:visit|visiting)\s+"
        rf"([A-Za-z][A-Za-z\s]+?)(?:\s+(?:{stop_words})\b|,|\.|$)",
        rf"\bto\s+([A-Za-z][A-Za-z\s]+?)(?:\s+(?:{stop_words})\b|,|\.|$)",
    ]

    for pattern in destination_patterns:
        match = re.search(pattern, request, re.IGNORECASE)
        if match:
            destination = _format_place(match.group(1))
            if destination:
                return destination

    if re.search(r"\btokyo\b", request, re.IGNORECASE):
        return "Tokyo"
    return "Tokyo"


@step()
def normalize_travel_request(request: str) -> dict[str, Any]:
    """Normalize loose demo travel requests into complete structured trip details."""
    normalized: dict[str, Any] = {
        "origin": "SFO",
        "destination": _simple_destination(request),
        "depart_date": "2026-07-10",
        "return_date": "2026-07-13",
        "guests": 2,
        "budget": 3000,
        "travel_style": "balanced",
        "original_request": request,
    }

    origin = _simple_origin(request)
    if origin:
        normalized["origin"] = origin

    dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", request)
    if dates:
        normalized["depart_date"] = dates[0]
    if len(dates) > 1:
        normalized["return_date"] = dates[1]

    guest_match = re.search(r"\bfor\s+(\d+)\s+(?:people|guests|travelers|travellers)\b", request, re.IGNORECASE)
    if guest_match:
        normalized["guests"] = int(guest_match.group(1))

    budget_match = re.search(r"\b(?:budget|under|around)\s*\$?([0-9][0-9,]*)\b", request, re.IGNORECASE)
    if budget_match:
        normalized["budget"] = int(budget_match.group(1).replace(",", ""))

    style_match = re.search(r"\b(luxury|budget|balanced|foodie|family|adventure|relaxed)\b", request, re.IGNORECASE)
    if style_match and style_match.group(1).lower() != "budget":
        normalized["travel_style"] = style_match.group(1).lower()

    return normalized


@function_tool
@step()
def record_planning_decision(next_action: str, rationale: str) -> str:
    """Record the coordinator's next specialist choice."""
    return _json({"next_action": next_action, "rationale": rationale})


@function_tool
@step()
def get_flight_quotes(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str,
) -> str:
    """Return deterministic flight quote records for a round trip."""
    quoted_at, expires_at = _quote_times()
    carriers = ["Aster Air", "Northline", "Blue Harbor"]
    quotes = []
    for index, carrier in enumerate(carriers, start=1):
        price = (
            260 + _stable_int(origin, destination, carrier, modulo=180) + (index * 35)
        )
        quotes.append(
            {
                "quote_id": f"flt-{_stable_int(origin, destination, carrier, modulo=99999):05d}",
                "carrier": carrier,
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date,
                "return_date": return_date,
                "selected_dates": [depart_date, return_date],
                "price": price,
                "currency": "USD",
                "quoted_at": quoted_at,
                "expires_at": expires_at,
            }
        )
    return _json(quotes)


@function_tool
@step()
def get_hotel_quotes(
    destination: str,
    check_in: str,
    check_out: str,
    guests: int = 2,
) -> str:
    """Return deterministic hotel quote records for a stay."""
    quoted_at, expires_at = _quote_times()
    hotels = ["Market House Hotel", "Canal & Co.", "The Observatory"]
    quotes = []
    for index, hotel in enumerate(hotels, start=1):
        nightly = 145 + _stable_int(destination, hotel, modulo=110) + (index * 20)
        quotes.append(
            {
                "quote_id": f"htl-{_stable_int(destination, hotel, modulo=99999):05d}",
                "hotel": hotel,
                "destination": destination,
                "check_in": check_in,
                "check_out": check_out,
                "selected_dates": [check_in, check_out],
                "guests": guests,
                "nightly_price": nightly,
                "price": nightly * 3,
                "currency": "USD",
                "quoted_at": quoted_at,
                "expires_at": expires_at,
            }
        )
    _crash_once_during_hotel(DBOS.workflow_id)
    return _json(quotes)


@function_tool
@step()
def get_local_activities(destination: str, travel_style: str = "balanced") -> str:
    """Return deterministic activity options for a destination."""
    quoted_at, expires_at = _quote_times()
    activities = [
        ("neighborhood food walk", 58),
        ("small museum pass", 34),
        ("half-day architecture tour", 82),
        ("sunset transit pass", 18),
    ]
    return _json(
        [
            {
                "quote_id": f"act-{_stable_int(destination, name, modulo=99999):05d}",
                "activity": name,
                "destination": destination,
                "travel_style": travel_style,
                "selected_dates": ["flexible"],
                "price": price
                + _stable_int(destination, travel_style, name, modulo=15),
                "currency": "USD",
                "quoted_at": quoted_at,
                "expires_at": expires_at,
            }
            for name, price in activities
        ]
    )


@function_tool
@step()
def review_trip_budget(
    flight_total: int,
    hotel_total: int,
    activity_total: int,
    budget: int,
) -> str:
    """Return a deterministic budget review for selected trip components."""
    total = flight_total + hotel_total + activity_total
    return _json(
        {
            "quote_id": f"bdg-{_stable_int(str(total), str(budget), modulo=99999):05d}",
            "selected_dates": ["itinerary"],
            "price": total,
            "budget": budget,
            "currency": "USD",
            "variance": budget - total,
            "status": "within_budget" if total <= budget else "over_budget",
            "quoted_at": _quote_times()[0],
            "expires_at": _quote_times()[1],
        }
    )


flight_researcher = Agent(
    name="flight_researcher",
    instructions=(
        "Research round-trip flights with get_flight_quotes. Return the best "
        "quote_id, dates, carrier, price, quoted_at, expires_at, and a brief rationale."
    ),
    tools=[get_flight_quotes],
)

hotel_researcher = Agent(
    name="hotel_researcher",
    instructions=(
        "Research hotels with get_hotel_quotes. Return the best quote_id, selected "
        "dates, hotel, price, quoted_at, expires_at, and a brief rationale."
    ),
    tools=[get_hotel_quotes],
)

local_planner = Agent(
    name="local_planner",
    instructions=(
        "Use get_local_activities to suggest a compact local plan. Include quote_id, "
        "activity names, prices, quoted_at, and expires_at."
    ),
    tools=[get_local_activities],
)

budget_reviewer = Agent(
    name="budget_reviewer",
    instructions=(
        "Use review_trip_budget to compare selected flight, hotel, and activity totals "
        "against the user's budget. Return status, variance, and any tradeoffs."
    ),
    tools=[review_trip_budget],
)

travel_planner = Agent(
    name="travel-concierge-planner",
    instructions=(
        "You are the travel concierge planning agent. Choose exactly one next action "
        "from flight, hotel, local, budget, or final. Use record_planning_decision "
        "exactly once. Prefer the most useful missing specialist for the normalized "
        "trip state. Do not choose final until flight, hotel, local, and budget are complete."
    ),
    tools=[record_planning_decision],
)

travel_coordinator = Agent(
    name="travel-concierge-coordinator",
    instructions=(
        "You are a travel concierge coordinator. Synthesize the normalized request "
        "and specialist findings into a practical final trip proposal. Include chosen "
        "quote-like records with quote_id, selected dates, price, quoted_at, expires_at, "
        "budget status, and a concise itinerary."
    ),
)

SPECIALIST_AGENTS = {
    "flight": flight_researcher,
    "hotel": hotel_researcher,
    "local": local_planner,
    "budget": budget_reviewer,
}


def _specialist_prompt(action: str, trip: dict[str, Any], findings: dict[str, str]) -> str:
    common = f"Normalized trip request:\n{_json(trip)}"
    if action == "flight":
        return (
            f"{common}\n\nCall get_flight_quotes exactly once with origin, destination, "
            "depart_date, and return_date from the normalized request. Choose the best quote."
        )
    if action == "hotel":
        return (
            f"{common}\n\nCall get_hotel_quotes exactly once with destination, check_in, "
            "check_out, and guests from the normalized request. Choose the best quote."
        )
    if action == "local":
        return (
            f"{common}\n\nCall get_local_activities exactly once with destination and "
            "travel_style from the normalized request. Choose a compact activity plan."
        )

    estimates = _estimate_budget_inputs(trip)
    return (
        f"{common}\n\nSpecialist findings so far:\n{_json(findings)}\n\n"
        f"Use these demo totals when calling review_trip_budget exactly once: {_json(estimates)}. "
        "Then explain whether the trip is within budget."
    )


def _estimate_budget_inputs(trip: dict[str, Any]) -> dict[str, int]:
    flight_price = 260 + _stable_int(trip["origin"], trip["destination"], "Aster Air", modulo=180) + 35
    hotel_price = (145 + _stable_int(trip["destination"], "Market House Hotel", modulo=110) + 20) * 3
    activity_total = sum(
        price + _stable_int(trip["destination"], trip["travel_style"], name, modulo=15)
        for name, price in [
            ("neighborhood food walk", 58),
            ("small museum pass", 34),
            ("half-day architecture tour", 82),
            ("sunset transit pass", 18),
        ]
    )
    return {
        "flight_total": flight_price,
        "hotel_total": hotel_price,
        "activity_total": activity_total,
        "budget": int(trip["budget"]),
    }


async def _plan_next_action(trip: dict[str, Any], completed: set[str], findings: dict[str, str]) -> str:
    result = await agentic_runner(
        starting_agent=travel_planner,
        input=(
            "Choose the next specialist for this travel workflow.\n\n"
            f"Required specialists: {', '.join(REQUIRED_SPECIALISTS)}\n"
            f"Completed specialists: {', '.join(sorted(completed)) or 'none'}\n"
            f"Normalized trip: {_json(trip)}\n"
            f"Findings so far: {_json(findings)}\n\n"
            "Return the recorded planning decision."
        ),
    )
    return choose_guarded_next_action(extract_planner_action(str(result.final_output)), completed)


@register_agent(name="travel-concierge")
async def travel_concierge(request: str) -> str:
    request, crash_during_hotel = _strip_hotel_crash_directive(request)
    if crash_during_hotel:
        _request_hotel_crash(DBOS.workflow_id)

    trip = normalize_travel_request(request)
    completed: set[str] = set()
    findings: dict[str, str] = {}

    for _ in range(MAX_COORDINATOR_DECISIONS):
        next_action = await _plan_next_action(trip, completed, findings)
        if next_action == "final":
            break

        logger.info("travel-concierge selected specialist: %s", next_action)
        specialist_result = await agentic_runner(
            starting_agent=SPECIALIST_AGENTS[next_action],
            input=_specialist_prompt(next_action, trip, findings),
        )
        findings[next_action] = str(specialist_result.final_output)
        completed.add(next_action)

        if len(completed) == len(REQUIRED_SPECIALISTS):
            break

    missing = [name for name in REQUIRED_SPECIALISTS if name not in completed]
    for action in missing:
        logger.info("travel-concierge guardrail selected missing specialist: %s", action)
        specialist_result = await agentic_runner(
            starting_agent=SPECIALIST_AGENTS[action],
            input=_specialist_prompt(action, trip, findings),
        )
        findings[action] = str(specialist_result.final_output)
        completed.add(action)

    result = await agentic_runner(
        starting_agent=travel_coordinator,
        input=(
            "Create the final travel concierge recommendation from this completed "
            f"specialist workflow.\n\nNormalized trip:\n{_json(trip)}\n\n"
            f"Specialist findings:\n{_json(findings)}"
        ),
    )
    final_output = str(result.final_output)
    logger.info("travel-concierge final output:\n%s", final_output)
    print(f"travel-concierge final output:\n{final_output}")
    return final_output
