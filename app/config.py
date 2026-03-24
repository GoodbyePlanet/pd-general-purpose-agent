from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    slack_bot_token: str
    slack_app_token: str
    anthropic_api_key: str
    anthropic_model: str = "claude-haiku-4-5-20251001"
    trigger_emoji: str = "pidi"
    log_level: str = "INFO"
    tavily_api_key: str = ""
    tavily_max_results: int = 3
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
