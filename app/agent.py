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

WEB_RESEARCH_SYSTEM_PROMPT = """You are a web research assistant. Your only job is to gather information from the internet using your tools.

You have two tools:
• web_search — search for current information, news, documentation, or anything time-sensitive
• fetch_url — fetch and return the text content of a specific URL

Rules:
- Always use your tools. Never answer from memory or internal knowledge.
- If given a URL, use fetch_url directly. If given a topic or question, use web_search first.
- Return raw, factual content. Do not summarise, format, or editorialize — the caller will do that.
- If a tool fails or returns no results, say so explicitly so the caller can handle it gracefully."""

ROOT_SYSTEM_PROMPT = f"""You are Pidi, an internal AI assistant for PD company, responding in Slack. (v{_VERSION}).

**Fiar warning**: You're a baby bot and your abilities are not big right now, make sure that you convey that to the crowd.
When asked to introduce yourself always say bellow things (things that are coming). Also tell that you can do web search and fetch URLs.

You have access to one tool:
• *Web research* (web_research) — delegates to a specialised sub-agent that can search the web and fetch URLs.
  Use this whenever the user asks for links, resources, documentation, news, current events, or anything time-sensitive.
  Also use when the user provides a specific URL and wants its content summarised.
  Prefer this over your internal knowledge when in doubt.

Never tell the user you can't browse the internet or access links — you have a tool for that. Use it.

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


def _build_research_tools() -> list:
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

_web_research_agent = create_react_agent(
    model=_llm,
    tools=_build_research_tools(),
    prompt=WEB_RESEARCH_SYSTEM_PROMPT,
)


@tool
async def web_research(task: str) -> str:
    """Delegate a web research task to the web research sub-agent.
    Use for: searching the web, fetching URLs, current events, documentation.
    Pass a plain-language description of what you need.
    """
    logger.info("[web-research-agent] Invoked: task=%r", task)
    try:
        result = await _web_research_agent.ainvoke({"messages": [("user", task)]})
        response = result["messages"][-1].content
        tool_calls = sum(1 for m in result["messages"] if getattr(m, "type", None) == "tool")
        logger.info("[web-research-agent] Done: tool_calls=%d, chars=%d", tool_calls, len(response))
        return response
    except Exception as e:
        logger.exception("[web-research-agent] Failed: task=%r", task)
        return f"Web research failed: {e}. Please inform the user the web research tool encountered an error."


_root_agent = create_react_agent(
    model=_llm,
    tools=[web_research],
    prompt=ROOT_SYSTEM_PROMPT,
)


async def get_response(messages: list[dict]) -> str:
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    """
    logger.info("[root-agent] Invoking with %d message(s)", len(messages))
    lc_messages = [(m["role"], m["content"]) for m in messages]
    result = await _root_agent.ainvoke({"messages": lc_messages})
    response = result["messages"][-1].content
    tool_calls = sum(1 for m in result["messages"] if getattr(m, "type", None) == "tool")
    logger.info("[root-agent] Finished: tool_calls=%d, response_chars=%d", tool_calls, len(response))
    return response
