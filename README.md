# Mortgage Analysis API

A FastAPI-based application for analyzing financial documents and providing mortgage simulation services.

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application and configuration
│   ├── config.py            # Application settings and configuration
│   ├── dependencies.py      # Dependency injection
│   ├── exceptions.py        # Custom exception classes
│   ├── models/              # Pydantic models
│   │   ├── __init__.py
│   │   ├── document.py      # Document-related models
│   │   └── mortgage.py      # Mortgage-related models
│   ├── routers/             # API route handlers
│   │   ├── __init__.py
│   │   └── mortgage.py      # Mortgage simulation endpoints
│   ├── services/            # Business logic services
│   │   ├── __init__.py
│   │   ├── gpt_service.py           # OpenAI GPT integration
│   │   ├── document_processor.py   # Azure Document Intelligence
│   │   ├── document_analysis.py    # Document analysis logic
│   │   └── mortgage_calculator.py  # Mortgage calculations
│   └── utils/               # Utility functions
│       ├── __init__.py
│       ├── text_processing.py      # Text chunking utilities
│       └── logging_config.py       # Logging configuration
├── requirements.txt         # Python dependencies
├── .env.example            # Environment variables template
└── README.md               # This file
```

## Features

- **Document Processing**: Supports PDF documents including payslips, tax certificates, and bank statements
- **AI-Powered Analysis**: Uses OpenAI GPT for document classification and data extraction
- **Mortgage Simulation**: Provides comprehensive mortgage eligibility calculations
- **Cross-Validation**: Validates data consistency across multiple documents
- **Hebrew Language Support**: Specialized for Israeli financial documents

## Requirements

- Python 3.9+
- OpenAI API key
- Azure Document Intelligence credentials (optional but recommended)

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and configure your environment variables:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` with your API keys and configuration

## Running the Application

### Development
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

- `GET /` - Root endpoint with API information
- `GET /health` - Health check endpoint
- `POST /mortgage/simulation` - Comprehensive mortgage simulation

## Configuration

The application uses Pydantic Settings for configuration management. All settings can be configured via environment variables or the `.env` file.

### Key Configuration Options

- `OPENAI_API_KEY` - Required for GPT services
- `AZURE_DOC_INTEL_ENDPOINT` & `AZURE_DOC_INTEL_KEY` - For document processing
- `DEBUG` - Enable debug mode
- `CORS_ORIGINS` - Allowed CORS origins
- `MAX_FILES_PER_REQUEST` - Maximum number of files per request
- `CHUNK_SIZE` - Text chunking size for large documents

## Architecture

The application follows clean architecture principles:

- **Routers**: Handle HTTP requests and responses
- **Services**: Contain business logic and external service integration
- **Models**: Define data structures using Pydantic
- **Dependencies**: Manage dependency injection
- **Utils**: Provide utility functions
- **Config**: Centralized configuration management

## Security Features

- Restricted CORS origins
- Input validation using Pydantic models
- Proper error handling and logging
- Environment-based configuration