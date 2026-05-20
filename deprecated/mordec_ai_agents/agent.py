import asyncio
import sys
from agents import Agent, function_tool
from dbos import DBOS, DBOSConfig
sys.path.insert(0, '../sdk/src')
from agents import Runner
from ddgs import DDGS
from sdk.decorators import step
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

@function_tool
@step()
def search_web(query: str) -> str:
    """Search the web for information about a topic. Returns titles, URLs, and summaries."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "No results found."
    formatted = []
    for r in results:
        formatted.append(f"Title: {r['title']}\nURL: {r['href']}\nSummary: {r['body']}")
    return "\n---\n".join(formatted)

agent = Agent(
    name="research-assistant",
    instructions="""You are a research assistant. Given a topic:
1. Search for information using search_web
2. Evaluate whether you have enough to write a thorough summary
3. If not, search again with a more specific or different query
4. Search at least twice before concluding
5. Synthesize findings into a clear, well-structured summary
Be explicit about what you found and what remains uncertain.""",
    tools=[search_web],
)

@DBOS.workflow()
async def run_agent(topic: str) -> str:
    result = await Runner.run(starting_agent=agent, input=f"Research this topic thoroughly: {topic}")
    return str(result.final_output)

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 agent.py <research topic>")
        sys.exit(1)

    topic = " ".join(sys.argv[1:])
    print(f"\nResearching: {topic}\n")
    output = await run_agent(topic)
    print("\n=== RESEARCH SUMMARY ===")
    print(output)

if __name__ == "__main__":
    _tp = TracerProvider()
    _tp.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:6006/v1/traces"))
    )
    trace.set_tracer_provider(_tp)
    OpenAIAgentsInstrumentor().instrument(tracer_provider=_tp)

    config: DBOSConfig = {
        "name": "research-assistant",
        "enable_otlp": True,
    }
    DBOS(config=config)
    DBOS.launch()
    asyncio.run(main())
    _tp.shutdown()
