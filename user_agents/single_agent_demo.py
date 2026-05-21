from agents import Agent, function_tool
from ddgs import DDGS

from sdk import register_agent, agentic_runner, sleep, step


@function_tool
@step()
def search_web(query: str) -> str:
    """Search the web for information about a topic. Returns titles, URLs, and summaries."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))

    if not results:
        return "No results found."

    formatted = []
    for result in results:
        formatted.append(
            f"Title: {result['title']}\n"
            f"URL: {result['href']}\n"
            f"Summary: {result['body']}"
        )

    return "\n---\n".join(formatted)


research_agent = Agent(
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


@register_agent(name="research-assistant")
async def research(topic: str) -> str:
    await sleep(30)
    result = await agentic_runner(
        starting_agent=research_agent,
        input=f"Research this topic thoroughly: {topic}",
    )
    return str(result.final_output)
