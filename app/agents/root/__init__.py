import logging

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from app.agents.root.prompt import ROOT_SYSTEM_PROMPT
from app.agents.web_research import web_research
from app.config import settings

logger = logging.getLogger(__name__)

_llm = ChatOpenAI(
    model=settings.openai_model,
    api_key=settings.openai_api_key,
)

_root_agent = create_agent(
    model=_llm,
    tools=[web_research],
    system_prompt=ROOT_SYSTEM_PROMPT,
)


async def get_response(messages: list[dict]) -> str:
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    """
    try:
        logger.info("[root-agent] Invoking with %d message(s)", len(messages))
        lc_messages = [(m["role"], m["content"]) for m in messages]
        result = await _root_agent.ainvoke({"messages": lc_messages})
        response = result["messages"][-1].content
        used_tools = [tc["name"] for m in result["messages"] if hasattr(m, "tool_calls") for tc in m.tool_calls]
        logger.info("[root-agent] Finished: tool_calls=%d %s, response_chars=%d", len(used_tools), used_tools,
                    len(response))

        return response
    except Exception as e:
        logger.exception("[root-agent] Failed")
        return f"Getting response failed: {e}. Please inform the user that something went wrong."
