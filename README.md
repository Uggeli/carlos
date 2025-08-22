# Carlos AI Assistant

An advanced AI assistant implementing the **Recursive Shard Architecture** that solves the stability-plasticity dilemma through architectural separation of memory and reasoning.

## Overview

Carlos uses a three-stage pipeline:
- **Curator**: Information gathering and context assembly
- **Thinker**: Deep analytical reasoning with internal dialogue
- **Response Generator**: Natural language output with TTS formatting

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
$env:FLASK_APP = "app.py"; $env:FLASK_ENV = "development"; python app.py
```

Open http://127.0.0.1:5000/

## Architecture

### Theoretical Foundation
Implements **"Shards of Thought"** framework separating:
- **Plasticity (Database)**: Factual, semantic, episodic memory in MongoDB
- **Stability (Network)**: Procedural, conceptual knowledge in model weights

This prevents catastrophic forgetting while enabling continuous learning.

### Key Features
- **Vector Search**: Automatic embedding generation and cosine similarity retrieval
- **Memory Persistence**: MongoDB storage with smart indexing
- **TTS Integration**: Bark TTS formatting with emotional markers
- **Context Management**: Topic-based conversation threading

## Development

### Testing
- Use `carlos_playground.ipynb` for interactive testing
- Use `tts_tests.ipynb` for TTS-related testing
- No formal test framework configured

### API
- **Endpoint**: `POST /api/chat`
- **Payload**: `{ "message": "..." }`
- **Response**: Includes Bark TTS formatting tags

## Documentation

- `CLAUDE.md`: Comprehensive development guide and architecture
- `ArchitecturePlans.md`: Detailed framework analysis
- `Thinker Model System Prompt.md`: Reasoning process definition
- `CuratorOutputs.md`: Example curator investigation outputs
