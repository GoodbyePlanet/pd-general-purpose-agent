import logging

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.agents.web_research.prompt import WEB_RESEARCH_SYSTEM_PROMPT
from app.agents.web_research.tools import _build_research_tools

logger = logging.getLogger(__name__)

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
        tool_names = [tc["name"] for m in result["messages"] if hasattr(m, "tool_calls") for tc in m.tool_calls]
        logger.info("[web-research-agent] Done: tool_calls=%d %s, chars=%d", len(tool_names), tool_names, len(response))
        return response
    except Exception as e:
        logger.exception("[web-research-agent] Failed: task=%r", task)
        return f"Web research failed: {e}. Please inform the user the web research tool encountered an error."
