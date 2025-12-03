# config.py
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: Optional[str] = None  # For DeepSeek: https://api.deepseek.com
    EMBEDDING_API_KEY: Optional[str] = None  # Separate key for embeddings (OpenAI)

    ES_HOST: str = "http://localhost:9200"
    ES_USERNAME: Optional[str] = None
    ES_PASSWORD: Optional[str] = None
    ES_INDEX_NAME: str = "demo_documents"

    APP_PORT: int = 8000

    EMBEDDING_MODEL: str = "text-embedding-3-small"
    CHAT_MODEL: str = "deepseek-chat"  # or gpt-4o-mini

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
