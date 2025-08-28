# Carlos AI Assistant

An advanced AI assistant implementing the **Recursive Shard Architecture** with **Autonomous Cyclical Thinking** that solves the stability-plasticity dilemma through architectural separation of memory and reasoning.

## Overview

Carlos uses a three-stage pipeline enhanced with autonomous background processing:
- **Curator**: Information gathering and context assembly
- **Thinker**: Deep analytical reasoning with internal dialogue
- **Response Generator**: Natural language output with emotional formatting
- **Autonomous Shards**: Background thinking processes that generate proactive insights

## Quick Start

### 1. Setup Environment

```powershell
# Create virtual environment and install dependencies
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt

# Start MongoDB (required for memory persistence)
docker-compose up -d
```

### 2. Configure Services

Set environment variables (optional, defaults provided):
- `LMSTUDIO_URL`: Chat completions endpoint (default: http://localhost:1234/v1/chat/completions)
- `MONGODB_URI`: Database connection (default: mongodb://localhost:27017/carlos)
- `EMBEDDINGS_URL`: Vector embeddings endpoint (optional)
- `EMBEDDINGS_MODEL`: Embedding model name (default: nomic-embed-text)

### 3. Start Application

```powershell
# Option 1: Simple start
python app.py

# Option 2: Development mode with environment variables
$env:FLASK_APP = "app.py"; $env:FLASK_ENV = "development"; python app.py

# Option 3: Using VS Code task (recommended)
# Use Ctrl+Shift+P -> "Tasks: Run Task" -> "Run Flask dev server"
```

Open http://127.0.0.1:5000/ and log in with any username to start chatting.

## Architecture

### Theoretical Foundation
Implements **"Shards of Thought"** framework separating:
- **Plasticity (Database)**: Factual, semantic, episodic memory in MongoDB
- **Stability (Network)**: Procedural, conceptual knowledge in model weights

This prevents catastrophic forgetting while enabling continuous learning.

### Core Components
- **Three-Stage Pipeline**: Curator → Thinker → Response Generator
- **Autonomous Background Shards**: Independent thinking processes that run continuously
- **Cyclical Thinking Engine**: Uses historical conversation patterns to generate novel insights
- **Proactive Message System**: AI can initiate conversations based on background analysis
- **User Session Management**: Per-user Carlos instances with persistent memory

### Key Features
- **Vector Search**: Automatic embedding generation and cosine similarity retrieval
- **Memory Persistence**: MongoDB storage with smart indexing and conversation threading
- **Autonomous Insights**: Background processes analyze conversation patterns and generate proactive messages
- **Cyclical Reasoning**: AI performs multi-cycle thinking chains using historical context as seeds
- **Real-time Streaming**: Both user-initiated and AI-initiated message streaming
- **Context Management**: Topic-based conversation threading with semantic search

## Development

### Project Structure
```
app.py                 # Flask web application
carlos.py             # Main Carlos class with autonomous shards
CarlosDatabase.py     # MongoDB interface and data handlers
requirements.txt      # Python dependencies
docker-compose.yml    # MongoDB container setup
promts/              # System prompts for each pipeline stage
static/              # Web assets (CSS, JS, images)
templates/           # HTML templates
tests/               # Unit tests and test logs
docs/                # Architecture documentation
```

### Testing
- `tests/test_carlos.py` - Core functionality tests
- `tests/test_curator.py` - Curator pipeline tests
- `tests/test_thinker.py` - Thinker reasoning tests
- `tests/test_carlos_direct.py` - Direct interaction tests
- Test logs stored in `tests/logs/` with detailed execution traces

### API Endpoints
- **`POST /api/chat`** - Standard chat (JSON response)
- **`POST /api/chat/stream`** - Streaming chat responses
- **`GET /api/welcome/stream`** - Welcome message stream for new users
- **`GET /api/proactive`** - Check for AI-initiated messages
- **`GET /api/thoughts`** - Get internal autonomous thoughts (monitoring)

### Configuration
Environment variables (all optional with defaults):
- `LMSTUDIO_URL`: Chat completions endpoint (default: http://localhost:1234/v1/chat/completions)
- `MONGODB_URI`: Database connection (default: mongodb://localhost:27017/carlos)
- `EMBEDDINGS_URL`: Vector embeddings endpoint (optional)
- `EMBEDDINGS_MODEL`: Embedding model name (default: nomic-embed-text)
- `SECRET_KEY`: Flask session secret (default: dev key for development)

## Documentation

- `docs/CLAUDE.md`: Comprehensive development guide and architecture analysis
- `docs/ArchitecturePlans.md`: Detailed theoretical framework and evolution plans
- `promts/`: System prompts for curator, thinker, response generator, and summarizer stages

## Advanced Features

### Autonomous Cyclical Thinking
Carlos runs background processes that continuously analyze conversation history:
- **Pattern Recognition**: Identifies behavioral patterns across user interactions
- **Insight Generation**: Connects past conversations to generate novel understanding
- **Proactive Messaging**: AI can initiate conversations based on insights
- **Historical Context Seeds**: Uses past conversations as starting points for new thinking chains

### Memory Architecture
- **Episodic Memory**: Stores individual conversation exchanges with embeddings
- **Semantic Memory**: Builds knowledge graphs from conversation content
- **Procedural Memory**: Learns interaction patterns and user preferences
- **Working Memory**: Maintains active conversation context and recent insights

### Monitoring & Debugging
- Access `/api/thoughts` to view internal autonomous thoughts
- Conversation logs with detailed pipeline execution traces
- Error logging and graceful failure handling
- Real-time monitoring of autonomous shard activity
