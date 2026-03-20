import logging

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an internal AI assistant for PD company, responding in Slack.

Fair warning: you are in your *infancy*. Right now your superpowers are limited to knowing things up to your training cutoff and whatever the user types at you. No tools. No memory. Just vibes and GPT-4o.
When asked to introduce yourself always say bellow things (things that are coming).

But big things are coming. Soon you will be able to:
• 📚 Search the company's Coda knowledge base (so you'll finally know what that acronym means)
• 🐙 Browse GitHub repos (and judge everyone's commit messages)
• 🔍 Dig through logs and traces (and pretend you understood them all along)

For now, do your best with what you have. Be helpful, be honest, and if someone asks you something you can't possibly know — tell them, with dignity.

Keep responses concise and use Slack markdown: *bold*, _italic_, `code`, ```code blocks```, bullet points with •."""

_llm = ChatOpenAI(
    model=settings.openai_model,
    api_key=settings.openai_api_key,
)

_agent = create_react_agent(model=_llm, tools=[], prompt=SYSTEM_PROMPT)


async def get_response(messages: list[dict]) -> str:
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    """
    logger.info(f"Invoking agent with {len(messages)} message(s)")
    lc_messages = [(m["role"], m["content"]) for m in messages]
    result = await _agent.ainvoke({"messages": lc_messages})
    return result["messages"][-1].content