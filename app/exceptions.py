"""Custom exceptions for the application."""

from typing import Optional, Any, Dict


class AppException(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class DocumentProcessingError(AppException):
    """Exception raised when document processing fails."""

    pass


class GPTServiceError(AppException):
    """Exception raised when GPT service fails."""

    pass


class DocumentAnalysisError(AppException):
    """Exception raised when document analysis fails."""

    pass


class ValidationError(AppException):
    """Exception raised when data validation fails."""

    pass


class ConfigurationError(AppException):
    """Exception raised when configuration is invalid."""

    pass


class ServiceUnavailableError(AppException):
    """Exception raised when a required service is unavailable."""

    pass
