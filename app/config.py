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

    # CORS Configuration - Disabled for development
    cors_origins: list[str] = ["*"]  # Allow all origins
    cors_allow_credentials: bool = False  # Must be False when using "*"
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    # Document Processing Configuration
    max_file_size_mb: int = 50
    max_files_per_request: int = 10
    chunk_size: int = 8000
    chunk_overlap_ratio: float = 0.25

    # Session Management Configuration
    session_db_path: str = "conversations.db"
    default_session_prefix: str = "mortgage_session_"

    # Chat Configuration
    max_message_length: int = 2000
    conversation_history_limit: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


# Global settings instance
settings = Settings()
