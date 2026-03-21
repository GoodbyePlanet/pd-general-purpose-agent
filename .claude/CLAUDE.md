# PD General Purpose Agent

## Project Overview

Internal Slack AI agent for PD company. Responds to @mentions and emoji reactions in Slack threads using GPT-4o via LangGraph.

## Tech Stack

- **Python 3.12+** with `uv` as package manager
- **FastAPI** — HTTP server (health checks, future APIs)
- **slack-bolt[async]** — Slack integration via Socket Mode (WebSocket)
- **LangGraph + LangChain** — Agent orchestration
- **langchain-openai** — GPT-4o LLM provider
- **pydantic-settings** — Configuration management
- **Docker** — Deployment on Hetzner VPS

## Project Structure

```
main.py                  # Entrypoint — runs uvicorn
app/
  config.py              # pydantic-settings config (loads .env)
  api.py                 # FastAPI app + lifespan (starts/stops Socket Mode)
  slack_app.py           # Slack AsyncApp + event handlers
  agent.py               # LangGraph agent + get_response()
docs/
  v1-plan.md             # Implementation plan
  v1-progress.md         # Progress tracker
```

## Commands

```bash
# Install dependencies
uv sync

# Run locally
uv run python main.py

# Docker
docker compose up --build
```

## Architecture Notes

- Single process, single uvicorn worker (mandatory for Socket Mode — multiple workers = duplicate events)
- FastAPI lifespan manages Socket Mode lifecycle: `connect_async()` on startup, `disconnect_async()` on shutdown
- LangGraph `create_react_agent` with empty tools list (ready for tool additions in V2)

## Configuration

All config via environment variables (see `.env.example`):
- `SLACK_BOT_TOKEN` — xoxb-... (Bot User OAuth Token)
- `SLACK_APP_TOKEN` — xapp-... (App-Level Token for Socket Mode)
- `OPENAI_API_KEY` — sk-...
- `OPENAI_MODEL` — default: gpt-4o
- `TRIGGER_EMOJI` — emoji name that triggers the bot (default: midi)

## Code Style

- Use async/await throughout — never block the event loop
- Keep it simple — no premature abstractions
- Error handling: try/except in Slack handlers, log exceptions, send "sorry" to a user
