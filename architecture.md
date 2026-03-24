# Architecture

## High-Level Overview

```mermaid
graph TB
    subgraph Slack
        U[User in Slack]
    end

    subgraph "Hetzner VPS (Docker)"
        subgraph "Single Process / Single Worker"
            SM[Socket Mode<br/>WebSocket]
            FA[FastAPI<br/>:8000]
            SH[Slack Event Handlers]
            RA[Root Agent<br/>Claude + ReAct]
            WRA[Web Research Agent<br/>Claude + ReAct]
        end
    end

    subgraph External APIs
        SAPI[Slack API]
        ANT[Anthropic API]
        TAV[Tavily Search API]
        WEB[Public Web]
    end

    U -- "@mention / emoji / thread reply" --> SAPI
    SAPI -- "WebSocket events" --> SM
    SM --> SH
    SH --> RA
    RA -- "tool call" --> WRA
    WRA -- "web_search()" --> TAV
    WRA -- "fetch_url()" --> WEB
    RA -. "LLM calls" .-> ANT
    WRA -. "LLM calls" .-> ANT
    SH -- "reply in thread" --> SAPI
    SAPI --> U
    FA -- "/health" --> FA
```

## Startup Sequence

```mermaid
sequenceDiagram
    participant main.py
    participant uvicorn
    participant FastAPI
    participant SocketMode
    participant Slack API

    main.py->>uvicorn: run("app.api:api", workers=1)
    uvicorn->>FastAPI: initialize app
    FastAPI->>FastAPI: enter lifespan()
    FastAPI->>SocketMode: connect_async()
    SocketMode->>Slack API: open WebSocket
    Slack API-->>SocketMode: connection established
    Note over FastAPI: Serving /health on :8000
    Note over SocketMode: Listening for Slack events
```

## Shutdown Sequence

```mermaid
sequenceDiagram
    participant uvicorn
    participant FastAPI
    participant SocketMode
    participant Slack API

    uvicorn->>FastAPI: SIGTERM / SIGINT
    FastAPI->>FastAPI: exit lifespan()
    FastAPI->>SocketMode: disconnect_async()
    SocketMode->>Slack API: close WebSocket
    Slack API-->>SocketMode: connection closed
```

## Event Handling

Three Slack events trigger the bot. Each resolves to a call to `get_response(messages)`.

```mermaid
flowchart TD
    E((Slack Event))

    E --> M{Event type?}

    M -->|app_mention| A1[handle_mention]
    M -->|reaction_added| A2[handle_reaction]
    M -->|message| A3[handle_thread_message]

    A1 --> C1{In a thread?}
    C1 -->|Yes| H1[Build full thread history]
    C1 -->|No| H2[Single message]

    A2 --> F1{Emoji == trigger?}
    F1 -->|No| SKIP1[Ignore]
    F1 -->|Yes| F2{From bot?}
    F2 -->|Yes| SKIP2[Ignore]
    F2 -->|No| H3[Fetch reacted message]

    A3 --> T1{Thread reply?}
    T1 -->|No| SKIP3[Ignore]
    T1 -->|Yes| T2{Has @mention?}
    T2 -->|Yes| SKIP4["Ignore (handled by app_mention)"]
    T2 -->|No| T3{Bot already in thread?}
    T3 -->|No| SKIP5[Ignore]
    T3 -->|Yes| H4[Build full thread history]

    H1 --> GR[get_response]
    H2 --> GR
    H3 --> GR
    H4 --> GR

    GR --> REPLY[Reply in thread]
```

## Multi-Agent Architecture

The agent layer uses a two-tier hierarchy built with LangChain's `create_agent`.

```mermaid
flowchart TB
    subgraph "Root Agent (Claude)"
        direction TB
        RP[System Prompt:<br/>You are Pidi, an internal AI assistant...]
        REACT1[ReAct Loop]
        RP --> REACT1
    end

    subgraph "Web Research Agent (Claude)"
        direction TB
        WRP[System Prompt:<br/>You are a web research assistant...]
        REACT2[ReAct Loop]
        WRP --> REACT2
    end

    subgraph Tools
        WS[web_search<br/>Tavily API]
        FU[fetch_url<br/>WebBaseLoader]
    end

    REACT1 -- "@tool web_research(task)" --> REACT2
    REACT2 --> WS
    REACT2 --> FU
    WS -- "search results" --> REACT2
    FU -- "page content (8k chars)" --> REACT2
    REACT2 -- "raw findings" --> REACT1
```

### Agent Call Sequence

```mermaid
sequenceDiagram
    participant Slack Handler
    participant Root Agent
    participant Anthropic
    participant Web Research
    participant Tavily
    participant Web

    Slack Handler->>Root Agent: get_response(messages)
    Root Agent->>Anthropic: messages + tools schema
    Anthropic-->>Root Agent: tool_call: web_research("...")

    Root Agent->>Web Research: web_research(task)
    Web Research->>Anthropic: task + tools schema
    Anthropic-->>Web Research: tool_call: web_search("...")

    Web Research->>Tavily: search(query)
    Tavily-->>Web Research: results[]

    Note over Web Research: May also call fetch_url()
    Web Research->>Web: GET url
    Web-->>Web Research: page content

    Web Research->>Anthropic: tool results
    Anthropic-->>Web Research: final summary
    Web Research-->>Root Agent: raw findings

    Root Agent->>Anthropic: tool result + context
    Anthropic-->>Root Agent: formatted Slack response
    Root Agent-->>Slack Handler: reply text
    Slack Handler->>Slack Handler: say() / chat_postMessage()
```

## Deployment

```mermaid
graph LR
    subgraph "Hetzner VPS"
        subgraph Docker
            C[Container: agent]
            C -- "port 8000" --> HC[Healthcheck<br/>GET /health<br/>every 30s]
        end
        ENV[.env file] -- "env_file" --> C
    end

    C -- "WebSocket" --> S[Slack API]
    C -- "HTTPS" --> O[Anthropic API]
    C -- "HTTPS" --> T[Tavily API]
```

| Component | Detail |
|-----------|--------|
| Base image | `python:3.12-slim` |
| Package manager | `uv` (copied from `ghcr.io/astral-sh/uv:latest`) |
| Workers | **1** (mandatory — multiple workers = duplicate Slack events) |
| Restart policy | `unless-stopped` |
| Health check | `GET /health` every 30s, 5s timeout, 3 retries |

## Project Structure

```
pd-general-purpose-agent/
├── main.py                          # Entrypoint — uvicorn (1 worker)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml                   # uv dependencies
├── .env.example
│
├── app/
│   ├── config.py                    # pydantic-settings (loads .env)
│   ├── api.py                       # FastAPI + lifespan (Socket Mode lifecycle)
│   ├── slack_app.py                 # 3 event handlers + thread history builder
│   │
│   └── agents/
│       ├── __init__.py              # Re-exports get_response()
│       ├── root/
│       │   ├── __init__.py          # Root agent + get_response()
│       │   └── prompt.py            # System prompt (reads version from pyproject.toml)
│       └── web_research/
│           ├── __init__.py          # Sub-agent exposed as @tool
│           ├── prompt.py            # System prompt
│           └── tools.py             # fetch_url, web_search
│
└── docs/                            # Planning & progress docs
```