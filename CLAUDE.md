# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI-based chatbot application for WB Digital Solutions, featuring:
- LangGraph-based conversation flow orchestration
- Qdrant vector database for context retrieval and conversation storage
- Redis caching for response optimization
- Multi-language support with automatic language detection

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application locally
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up --build

# Run in detached mode
docker-compose up -d

# Stop services
docker-compose down
```

## Architecture Overview

### Core Components

1. **main.py**: FastAPI application entry point
   - `/chat` endpoint for handling chat requests
   - Manages Qdrant collections initialization
   - Implements response caching with Redis

2. **graph_config.py**: LangGraph workflow definition
   - Defines conversation state machine
   - Routes intents to appropriate processing nodes
   - Orchestrates the complete conversation flow

3. **nodes.py**: Processing nodes for the conversation graph
   - Intent detection (greeting, services inquiry, quote request)
   - Context retrieval from Qdrant
   - Response generation using DeepSeek API

### Data Flow

1. User message → Intent Detection
2. Based on intent:
   - Greeting → Direct greeting response
   - Services/Quote → Retrieve company context → Generate augmented response
3. Response revision for clarity and formatting
4. Save conversation to Qdrant for future context
5. Cache response in Redis

### External Services

- **Qdrant**: Vector database for storing company information and chat logs
- **Redis**: Response caching (7-day TTL)
- **DeepSeek API**: LLM for intent detection and response generation
- **Sentence Transformers**: Generates embeddings (all-MiniLM-L6-v2, 384 dimensions)

## Environment Variables

Required in `.env` file:
- `DEEPSEEK_API_KEY`: API key for DeepSeek LLM
- `QDRANT_HOST`: Qdrant server URL
- `QDRANT_API_KEY`: Qdrant authentication key
- `REDIS_HOST`: Redis server host (default: localhost)
- `REDIS_PORT`: Redis server port (default: 6379)
- `REDIS_DB`: Redis database number (default: 0)

## Key Implementation Details

- **Vector Dimensions**: All embeddings use 384 dimensions (all-MiniLM-L6-v2)
- **Collections**: `company_info` (static company data) and `chat_logs` (conversation history)
- **Response Caching**: SHA256 hash of user input as cache key
- **Language Detection**: Automatic detection for Portuguese, English, Spanish, and Italian
- **Response Limits**: Revised responses limited to 600 characters