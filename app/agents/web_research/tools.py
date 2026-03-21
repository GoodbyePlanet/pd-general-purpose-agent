import logging

from langchain_community.document_loaders import WebBaseLoader
from langchain_core.tools import tool
from tavily import TavilyClient

from app.config import settings

logger = logging.getLogger(__name__)

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
