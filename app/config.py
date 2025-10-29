import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


if Path(".env.dev").exists():
    load_dotenv(".env.dev", override=False)

load_dotenv(".env", override=False)

_ENVIRONMENT = os.getenv("ENVIRONMENT")

if not _ENVIRONMENT:
    raise RuntimeError(
        "ENVIRONMENT must be set (via environment variables or .env files) before starting the app."
    )

ENVIRONMENT = _ENVIRONMENT.lower()
ENV_FILE = ".env.dev" if ENVIRONMENT == "dev" else ".env"


class Settings(BaseSettings):
    """Application settings with environment variable loading."""

    # API Configuration
    app_name: str = "mortgage-broker"
    app_version: str = "1.0.0"
    debug: bool = False

    # OpenAI Configuration
    openai_api_key: Optional[str] = None

    # Azure Document Intelligence Configuration
    azure_doc_intel_endpoint: Optional[str] = None
    azure_doc_intel_key: Optional[str] = None

    # CORS Configuration
    cors_origins: list[str] = ["http://localhost:5173"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    # Document Processing Configuration
    max_files_per_request: int = 10

    # Supabase Auth Configuration
    supabase_project_url: Optional[str] = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: Optional[str] = None
    supabase_jwks_url: Optional[str] = None
    supabase_jwks_cache_ttl_seconds: int = 300

    # Database Configuration (Supabase direct connection)
    db_host: Optional[str] = Field(default=None, alias="host")
    db_port: int = Field(default=5432, alias="port")
    db_name: Optional[str] = Field(default=None, alias="dbname")
    db_user: Optional[str] = Field(default=None, alias="user")
    db_password: Optional[str] = Field(default=None, alias="password")
    environment: str = ENVIRONMENT

    # Session Management Configuration
    default_session_prefix: str = "mortgage_session_"
    session_max_entries: int = 500
    session_ttl_minutes: int = 180

    # Chat Configuration
    max_message_length: int = 2000
    chat_api_key: str | None = None
    agent_max_turns: int = 30

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
