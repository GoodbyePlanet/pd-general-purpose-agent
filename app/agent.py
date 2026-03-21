import logging
import tomllib
from pathlib import Path

from langchain_community.document_loaders import WebBaseLoader
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from tavily import TavilyClient

from app.config import settings

logger = logging.getLogger(__name__)

def _read_version() -> str:
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        return tomllib.load(f)["project"]["version"]

_VERSION = _read_version()

SYSTEM_PROMPT = f"""You are Pidi, an internal AI assistant for PD company, responding in Slack. (v{_VERSION}).

**Fiar warning**: You're a baby bot and your abilities are not big right now, make sure that you convey that to the crowd.
When asked to introduce yourself always say bellow things (things that are coming). Also tell that you can do web_search and fetching from URLs.

You have access to two tools:
• *Web search* (web_search) — use this whenever the user asks for links, resources, documentation, or more detail on a topic; also use for current events, recent news, or anything time-sensitive; prefer this over your internal knowledge when in doubt
• *URL fetch* (fetch_url) — use when the user provides a specific URL and wants its content summarized or discussed; also use when a user reacts to a Slack message containing a URL

Never tell the user you can't browse the internet or access links — you have tools for that. Use them.

Big things are still coming:
• 📚 Search the company's Coda knowledge base
• 🐙 Browse GitHub repos
• 🔍 Dig through logs and traces

Keep responses concise and use Slack markdown: *bold*, _italic_, `code`, ```code blocks```, bullet points with •."""

_tavily_client = TavilyClient(api_key=settings.tavily_api_key) if settings.tavily_api_key else None


@tool
def fetch_url(url: str) -> str:
    """Fetch the content of a URL and return it as plain text."""
    logger.info("fetch_url called: url=%s", url)
    docs = WebBaseLoader(url).load()
    if not docs:
        logger.warning("fetch_url: no content returned for url=%s", url)
        return "Could not fetch URL."
    content = docs[0].page_content[:8000]
    logger.info("fetch_url: fetched %d chars from url=%s", len(content), url)
    return content


@tool
def web_search(query: str) -> str:
    """Search the web for current information, news, or anything time-sensitive."""
    logger.info("web_search called: query=%r", query)
    results = _tavily_client.search(query, max_results=settings.tavily_max_results)
    hits = results.get("results", [])
    logger.info("web_search: got %d results for query=%r", len(hits), query)
    return "\n\n".join(
        f"{r['title']}\n{r['url']}\n{r['content']}"
        for r in hits
    )


def _build_tools() -> list:
    tools = [fetch_url]

    if not settings.tavily_api_key:
        logger.warning("Tavily API key not set — web search disabled.")
        return tools

    logger.info("Search enabled with Tavily, max_results=%d", settings.tavily_max_results)
    tools.append(web_search)
    return tools


_llm = ChatOpenAI(
    model=settings.openai_model,
    api_key=settings.openai_api_key,
)

_agent = create_react_agent(model=_llm, tools=_build_tools(), prompt=SYSTEM_PROMPT)


async def get_response(messages: list[dict]) -> str:
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    """
    logger.info("Invoking agent with %d message(s)", len(messages))
    lc_messages = [(m["role"], m["content"]) for m in messages]
    result = await _agent.ainvoke({"messages": lc_messages})
    response = result["messages"][-1].content
    tool_calls = sum(1 for m in result["messages"] if getattr(m, "type", None) == "tool")
    logger.info("Agent finished: tool_calls=%d, response_chars=%d", tool_calls, len(response))
    return response
