# PD General Purpose Agent - V1 Implementation Plan

## Context

PD company needs an internal AI assistant accessible via Slack. People can @mention the bot or add an emoji reaction to any message, and the agent replies in the thread with an LLM-generated response. V1 focuses purely on Slack integration with GPT-4o — no RAG, no external tools yet. Future iterations will add Coda knowledge, GitHub repos, logs/traces, etc.

## Architecture

Single Python process running two async workloads on one event loop:

1. **FastAPI** (uvicorn) — health endpoint, future APIs
2. **Slack Bolt `AsyncSocketModeHandler`** — WebSocket connection to Slack (no public URL needed)

When an event arrives (mention or emoji reaction), the handler calls a LangGraph agent → GPT-4o → posts reply in Slack thread.

## Project Structure

```
pd-general-purpose-agent/
  pyproject.toml              # add dependencies
  .env.example                # template for secrets
  .gitignore                  # add .env
  Dockerfile
  docker-compose.yml
  main.py                     # entrypoint (uvicorn)
  app/
    __init__.py
    config.py                 # pydantic-settings config
    slack_app.py              # AsyncApp + event handlers
    agent.py                  # LangGraph agent
    api.py                    # FastAPI app + lifespan
```

## Dependencies

```
slack-bolt[async]>=1.18,<2
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
langgraph>=0.4,<1
langchain-openai>=0.3,<1
pydantic-settings>=2.5,<3
```

## Implementation Steps

### Step 1: Dependencies & Config
- Update `pyproject.toml` with dependencies, run `uv sync`
- Create `app/__init__.py`, `app/config.py` with pydantic-settings (SLACK_BOT_TOKEN, SLACK_APP_TOKEN, OPENAI_API_KEY, OPENAI_MODEL, TRIGGER_EMOJI, LOG_LEVEL, HOST, PORT)
- Create `.env.example`, update `.gitignore` with `.env`
- **Verify**: import config with a test `.env`

### Step 2: FastAPI Health Endpoint
- Create `app/api.py` with FastAPI app and `/health` endpoint
- Rewrite `main.py` as uvicorn entrypoint (workers=1, mandatory for Socket Mode)
- **Verify**: `curl localhost:8000/health` → `{"status":"ok"}`

### Step 3: Slack App Setup (Manual)
- Create Slack App at api.slack.com/apps
- Enable Socket Mode → get `xapp-...` token
- Subscribe to bot events: `app_mention`, `reaction_added`
- Bot token scopes: `app_mentions:read`, `channels:history`, `groups:history`, `chat:write`, `reactions:read`
- Install to workspace → get `xoxb-...` token
- Add tokens to `.env`

### Step 4: Slack Bot with Stub Responses
- Create `app/slack_app.py` with `AsyncApp`
- Add `app_mention` handler that echoes the message back in thread
- Wire Socket Mode into FastAPI lifespan (`connect_async()` on startup, `disconnect_async()` on shutdown)
- **Verify**: @mention bot in Slack → get echo reply in thread

### Step 5: LangGraph Agent
- Create `app/agent.py` with `create_react_agent` (empty tools list, GPT-4o)
- System prompt: personality-forward Slack assistant with Slack markdown, concise responses; teases upcoming capabilities (Coda, GitHub, logs/traces)
- Expose single `async get_response(messages: list[dict]) -> str` — takes full conversation history as `[{"role": "user"|"assistant", "content": str}]` instead of a plain string, enabling multi-turn context
- **Verify**: test script calling `get_response([{"role": "user", "content": "hello"}])` returns GPT-4o reply

### Step 6: Wire Agent into Handlers
- Add `build_thread_history(client, channel, thread_ts, bot_user_id) -> list[dict]` helper:
  - Fetches full thread via `conversations_replies`
  - Strips `<@mention>` prefixes, truncates each message to 4000 chars
  - Tags each message as `"assistant"` (bot) or `"user"` based on `bot_id`/`user_id`
- Replace stub echo in `app_mention` handler with `get_response()` call:
  - If in an existing thread (`thread_ts` present): fetch full thread history via `build_thread_history` and pass to agent
  - If a new top-level mention: send just the current stripped message
- Add `reaction_added` handler:
  - Filter on configured trigger emoji
  - Fetch original message via `conversations_history(latest=ts, inclusive=True, limit=1)`
  - Skip if message is from the bot itself (prevent loops)
  - Call `get_response()` with single-message history
  - Post reply in thread via `chat_postMessage`
- Add `message` event handler (`handle_thread_message`) for thread continuity:
  - Fires on any message in a thread the bot is already participating in
  - Skips: top-level posts, bot messages, subtypes, messages containing `<@mention>` (handled by `app_mention`)
  - Fetches full thread history; if no prior bot message found, silently skips
  - Calls `get_response()` with full history and replies in thread
- All handlers: try/except with error logging + "sorry" fallback to user
- **Verify**: @mention → LLM reply; reply in thread → bot continues conversation; emoji reaction → LLM reply in thread

### Step 7: Docker & Deploy
- Create `Dockerfile` (python:3.12-slim, uv for deps)
- Create `docker-compose.yml` (restart policy, health check, env_file)
- **Verify**: `docker compose up` works locally
- Deploy to Hetzner: `git pull && docker compose up -d --build`

### Step 8: Polish
- Update `.gitignore` comprehensively
- Clean up README with setup instructions

## Key Design Decisions

- **Socket Mode + FastAPI lifespan**: Use `connect_async()` (not `start_async()`) so the socket handler runs on the same event loop as uvicorn without blocking
- **Single uvicorn worker**: Mandatory — multiple workers = duplicate Slack event processing
- **LangGraph from day 1**: Even with no tools, using `create_react_agent` means adding tools later is a one-line change
- **Module-level agent singleton**: The LangGraph graph is stateless and safe to share
- **Conversation history over single message**: `get_response` accepts `list[dict]` so the agent has full thread context; this is a one-time change that unlocks multi-turn conversations for all handlers
- **`reload=True` in dev**: uvicorn `reload=True` in `main.py` for fast local iteration; should be disabled in production
- **Thread continuity via `message` event**: Bot replies to any message in a thread it's already in, without requiring an explicit @mention every time

## Edge Cases to Handle

- Strip `<@U12345>` mention prefix from message text before sending to LLM
- Bot reacting to its own messages → check `bot_id` on fetched message, skip if it's ours
- Emoji on message in channel bot isn't in → `conversations_history` fails, handle gracefully
- Long messages → truncate to ~4000 chars before sending to LLM
- Empty messages after stripping mention → ignore silently
- `message` event fires on all channel messages including bot's own → guard with `bot_id`/`subtype` checks
- `message` events containing `<@mention>` must be skipped — they're handled by `app_mention` to avoid double responses
- Thread reply without prior bot participation → fetch history, check for any `"assistant"` role before the last message, skip if none found

## Verification

1. Start locally: `uv run python main.py`
2. Health check: `curl http://localhost:8000/health`
3. Go to Slack, @mention the bot → should reply in thread with GPT-4o response
4. Add the configured emoji (default: :robot_face:) to any message → bot replies in thread
5. Docker: `docker compose up --build` → same behavior
