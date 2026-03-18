from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    slack_bot_token: str
    slack_app_token: str
    openai_api_key: str
    openai_model: str = "gpt-4o"
    trigger_emoji: str = "robot_face"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
