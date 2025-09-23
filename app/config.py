from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable loading."""

    # API Configuration
    app_name: str = "Mortgage Analysis API"
    app_version: str = "1.0.0"
    debug: bool = False

    # OpenAI Configuration
    openai_api_key: Optional[str] = None

    # Azure Document Intelligence Configuration
    azure_doc_intel_endpoint: Optional[str] = None
    azure_doc_intel_key: Optional[str] = None

    # CORS Configuration - relaxed defaults for development
    cors_origins: list[str] = ["*"]  # Allow all origins
    cors_allow_credentials: bool = False  # Must be False when using "*"
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    # Document Processing Configuration
    max_files_per_request: int = 10

    # Session Management Configuration
    default_session_prefix: str = "mortgage_session_"

    # Chat Configuration
    max_message_length: int = 2000

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


# Global settings instance
settings = Settings()
