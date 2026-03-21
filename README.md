# PD General Purpose Agent

Internal Slack AI assistant for PD company. Responds to @mentions and emoji reactions in Slack threads using GPT-4o via LangGraph.

## How it works

- **@mention** the bot in any channel → it replies in thread
- **React with the trigger emoji** (default: `pidi`) to any message → it replies in thread

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description                                        |
|----------|----------------------------------------------------|
| `SLACK_BOT_TOKEN` | `xoxb-...` Bot User OAuth Token                    |
| `SLACK_APP_TOKEN` | `xapp-...` App-Level Token (Socket Mode)           |
| `OPENAI_API_KEY` | `sk-...` OpenAI API key                            |
| `OPENAI_MODEL` | LLM model (default: `gpt-4o`)                      |
| `TRIGGER_EMOJI` | Emoji name that triggers the bot (default: `pidi`) |
| `LOG_LEVEL` | Log level (default: `INFO`)                        |

### 3. Run locally

```bash
uv run python main.py
```

Health check: `curl http://localhost:8000/health`

### 4. Run with Docker

```bash
docker compose up --build
```

## Slack App requirements

The Slack app needs the following configuration:

**Bot token scopes:** `app_mentions:read`, `channels:history`, `groups:history`, `chat:write`, `reactions:read`

**Event subscriptions:** `app_mention`, `reaction_added`

**Socket Mode:** enabled (requires an App-Level Token with `connections:write` scope)