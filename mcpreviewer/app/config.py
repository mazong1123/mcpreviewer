from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_app_id: int = 0
    github_private_key: str = ""
    github_webhook_secret: str = ""
    log_level: str = "INFO"
    port: int = 8000

    model_config = {"env_prefix": "", "env_file": ".env"}
