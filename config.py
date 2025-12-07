# config.py
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: Optional[str] = None  # For DeepSeek: https://api.deepseek.com
    OPENAI_API_KEY: Optional[str] = None  # Separate key for embeddings (OpenAI)

    ES_HOST: str = "http://localhost:9200"
    ES_USERNAME: Optional[str] = None
    ES_PASSWORD: Optional[str] = None
    ES_INDEX_NAME: str = "demo_documents"

    APP_PORT: int = 8000

    EMBEDDING_MODEL: str = "text-embedding-3-small"
    CHAT_MODEL: str = "deepseek-chat"  # or gpt-4o-mini
    LLM_MAX_TOKENS: int = 2048  # Max tokens for DeepSeek chat completions (configurable)

    @field_validator("ES_USERNAME", "ES_PASSWORD", "DEEPSEEK_BASE_URL", "OPENAI_API_KEY", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty strings to None"""
        if v == "" or v is None:
            return None
        return v

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
