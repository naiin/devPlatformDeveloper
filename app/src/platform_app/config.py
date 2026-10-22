from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    app_version: str = "development"
    root_path: str = ""
    stream: str = "platform:jobs"
    consumer_group: str = "platform-workers"
    reclaim_idle_ms: int = Field(default=30_000, ge=0)
    outbox_retry_seconds: int = Field(default=60, ge=0)


@lru_cache
def settings() -> Settings:
    return Settings()
