# V2 Progress

## Steps

| # | Step | Status |
|---|------|--------|
| 1 | `uv add langchain-community tavily-python beautifulsoup4 lxml` | Done |
| 2 | Add `tavily_api_key`, `tavily_max_results` to `app/config.py` (`enable_search` removed — key presence controls search) | Done |
| 3 | Add `fetch_url` tool, `web_search` tool, `_build_tools()`, update `SYSTEM_PROMPT`, pass tools to agent in `app/agent.py` | Done |
| 4 | Update `.env.example` with new vars | Done |
| 5 | Verify locally (start bot, test in Slack) | Done |

## Notes

**`TavilySearchResults` → raw `TavilyClient`**
The plan called for `TavilySearchResults` from `langchain-community`. Switched to a custom `@tool` wrapping `TavilyClient` directly to control output format — title + URL + snippet joined as plain text is easier for the LLM to read and cite than a raw list of dicts.

**System prompt debugging**
Bot was still responding "I don't have browsing capabilities" after adding tools. Root cause: GPT-4o has a trained reflex to say it can't browse the internet, even when tools are bound. The system prompt now includes an explicit override: "Never tell the user you can't browse the internet or access links — you have tools for that. Use them." Confirmed working via local test (`asyncio.run(get_response(...))`).

**Slack URL format**
Slack sends URLs in the format `<https://url|label>`. Confirmed the LLM handles this correctly without any preprocessing — it extracts the real URL before calling `fetch_url`.