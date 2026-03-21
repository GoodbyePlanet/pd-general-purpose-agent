# V2: Internet Search via Tavily + URL Fetching via WebBaseLoader

## Context

The V1 agent was deployed with `tools=[]` — a stub ready for V2 tool additions. The agent cannot answer questions about recent events or anything outside its training data. V2 adds two tools: web search (Tavily) for general queries, and URL fetching (WebBaseLoader) so the agent can read the actual content of a specific link — e.g. when a user reacts to a Slack message containing a URL.

---

## Approach

Use a custom `web_search` tool wrapping `TavilyClient` directly (from `tavily-python`) for web search, and a custom `fetch_url` tool backed by `WebBaseLoader` for reading specific URLs. Both tools are added to the `create_react_agent` tools list. The agent's behavior and all Slack handler code remain unchanged — only `agent.py`, `config.py`, `.env.example`, and `pyproject.toml` are touched.

`WebBaseLoader` fetches a URL, strips HTML, and returns plain text — no API key required. The LLM decides autonomously when to search vs. fetch a URL vs. answer from memory.

---

## Implementation Steps

### 1. Add packages

```bash
uv add langchain-community tavily-python beautifulsoup4 lxml
```

`beautifulsoup4` and `lxml` are required by `WebBaseLoader` to parse HTML.

### 2. `app/config.py` — add 2 new fields to `Settings`

```python
tavily_api_key: str = ""       # empty = search disabled
tavily_max_results: int = 3
```

`tavily_api_key` defaults to `""` (not required) so the bot starts cleanly in environments without search configured.

### 3. `app/agent.py` — key changes

- Add imports: `TavilyClient`, `WebBaseLoader`, `tool` decorator
- Initialize `_tavily_client` once at module level (not per-call)
- Add `fetch_url` custom tool backed by `WebBaseLoader`
- Add `web_search` custom tool wrapping `TavilyClient`
- Add `_build_tools()` — always includes `fetch_url`, adds `web_search` only if key is set
- Pass `_build_tools()` result to `create_react_agent`
- Update `SYSTEM_PROMPT` to reflect both tools

**`fetch_url` tool:**
```python
@tool
def fetch_url(url: str) -> str:
    """Fetch the content of a URL and return it as plain text."""
    docs = WebBaseLoader(url).load()
    if not docs:
        return "Could not fetch URL."
    return docs[0].page_content[:8000]
```

**`web_search` tool:**
```python
_tavily_client = TavilyClient(api_key=settings.tavily_api_key) if settings.tavily_api_key else None

@tool
def web_search(query: str) -> str:
    """Search the web for current information, news, or anything time-sensitive."""
    results = _tavily_client.search(query, max_results=settings.tavily_max_results)
    hits = results.get("results", [])
    return "\n\n".join(
        f"{r['title']}\n{r['url']}\n{r['content']}"
        for r in hits
    )
```

**`_build_tools()` logic:**
```python
def _build_tools() -> list:
    tools = [fetch_url]
    if not settings.tavily_api_key:
        logger.warning("Tavily API key not set — web search disabled.")
        return tools
    logger.info("Search enabled with Tavily, max_results=%d", settings.tavily_max_results)
    tools.append(web_search)
    return tools
```

**Updated `SYSTEM_PROMPT`:**
```
You are an internal AI assistant for PD company, responding in Slack.

You have access to two tools:
• *Web search* (web_search) — use whenever the user asks for links, resources, documentation,
  or more detail on a topic; also for current events, recent news, or anything time-sensitive;
  prefer this over internal knowledge when in doubt
• *URL fetch* (fetch_url) — use when the user provides a specific URL and wants its content
  summarized or discussed; also when a user reacts to a Slack message containing a URL

Never tell the user you can't browse the internet or access links — you have tools for that. Use them.

Keep responses concise and use Slack markdown: *bold*, _italic_, `code`, ```code blocks```, bullet points with •.
```

**Updated agent initialization:**
```python
_agent = create_react_agent(model=_llm, tools=_build_tools(), prompt=SYSTEM_PROMPT)
```

### 4. `.env.example` — add new vars

```
TAVILY_API_KEY=tvly-your-key-here
TAVILY_MAX_RESULTS=3
```

---

## Key Decisions

**`TavilyClient` directly vs `TavilySearchResults` from langchain-community**

The initial plan was to use `TavilySearchResults` (a pre-built LangChain tool). Switched to a raw `TavilyClient` wrapped in a custom `@tool` for two reasons:
1. More control over the output format — `TavilySearchResults` returns a list of dicts, while the custom wrapper formats title + URL + snippet as plain text, which is easier for the LLM to read and cite
2. Explicit output shape makes it easier to debug and tune (e.g., adjusting the truncation, adding metadata)

**Module-level `_tavily_client` initialization**

`TavilyClient` is initialized once at import time rather than inside the tool function. This avoids re-instantiating the client on every tool call and makes it easy to check at startup whether Tavily is configured (via the `_build_tools()` log line).

**`_build_tools()` pattern instead of inline conditional**

The tool list is built in a dedicated function rather than an inline expression to keep `create_react_agent(...)` readable and to make it easy to add more optional tools (e.g., Coda search in V3) with the same conditional pattern.

**System prompt emphasis on "never say you can't browse"**

Without an explicit instruction, GPT-4o defaults to saying "I don't have browsing capabilities" even when tools are bound — it's a trained reflex from RLHF. The "Never tell the user you can't browse the internet" line overrides this. Verified during debugging: locally the agent worked correctly once this instruction was in place.

**8000-char truncation in `fetch_url`**

`WebBaseLoader` can return very large pages. 8000 chars fits comfortably within context and is enough for the LLM to summarize most READMEs, docs pages, and GitHub repos without hitting token limits.

---

## Critical Files

- `app/agent.py` — add `fetch_url` tool, `web_search` tool, `_build_tools()`, update `SYSTEM_PROMPT`, pass tools to agent
- `app/config.py` — add `tavily_api_key`, `tavily_max_results`
- `.env.example` — document new vars
- `pyproject.toml` — updated via `uv add` (not manual edit)

**No changes needed:** `app/slack_app.py`, `app/api.py`, `main.py` — all callers of `get_response()` stay untouched.

---

## Notes

- Both tools are synchronous. LangGraph's `create_react_agent` handles sync tools transparently via `run_in_executor`. No async wrappers needed.
- `fetch_url` requires no API key — always available.
- `WebBaseLoader` requires `beautifulsoup4` and `lxml` to parse HTML.
- Tool errors (bad API key, network failure, unreachable URL) surface as tool call failures inside the ReAct loop — the agent may still respond gracefully. Visible in logs.
- To disable web search, remove or leave `TAVILY_API_KEY` empty — `fetch_url` still works.
- Slack formats URLs as `<https://url|label>` in message payloads. The LLM handles this format correctly and extracts the real URL before calling `fetch_url`.

---

## Verification

1. Set `TAVILY_API_KEY` in `.env`
2. `uv run python main.py`
3. Check startup logs: should see `"Search enabled with Tavily, max_results=3"`
4. In Slack, `@mention` the bot with a question about a recent event — bot should use `web_search` and return sourced results
5. In Slack, `@mention` the bot with a specific URL — bot should call `fetch_url` and summarize the page
6. Test search disable: remove `TAVILY_API_KEY`, restart, verify log warns `"Tavily API key not set."` — `fetch_url` should still work