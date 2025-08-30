# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
# source .venv/bin/activate    # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### Database Setup
```bash
# Start MongoDB container
docker-compose up -d

# Reset user database (if needed)
python reset_db.py --user username

# Reset all Carlos databases
python reset_db.py --all

# List existing databases
python reset_db.py --list

# Reset collections only (preserve database)
python reset_db.py --collections username
```

### Running the Application
```bash
# FastAPI development mode (recommended)
uvicorn app:app --reload

# Alternative: Direct Python execution
python app.py

# Install FastAPI dependencies if needed
pip install fastapi "uvicorn[standard]"
```

### Testing and Debugging
- No formal test framework configured
- Use interactive testing with direct Carlos instance creation
- Monitor database state with `reset_db.py --list`

## Architecture Overview

### Core Philosophy: Recursive Shard Architecture

Carlos implements a **"Shards of Thought"** framework that solves the stability-plasticity dilemma through architectural separation:

- **Plasticity (Database)**: Factual, semantic, and episodic memory stored in MongoDB - allows continuous learning without forgetting
- **Stability (Network)**: Procedural and conceptual knowledge in model weights - maintains stable reasoning patterns

### The Multi-Agent Pipeline

**Main Carlos Class (`carlos.py:427-687`)**
- Orchestrates the complete interaction pipeline
- Manages MongoDB database operations through `CarlosDatabaseHandler`
- Handles async operations with httpx client
- Implements message chunking for long inputs (4000+ chars)
- Provides both streaming and non-streaming response modes

**Stage 1: CuratorAgent (`carlos.py:92-110`)**
- Analyzes incoming messages for information needs
- Determines what queries to execute against stored knowledge
- Returns `queries_to_execute` and `insights_to_store`

**Stage 2: ThinkerAgent (`carlos.py:112-126`)**
- Performs deep analytical reasoning using curator-provided context
- Iterative thinking loop (max 5 cycles) until context is sufficient
- Returns reasoning, information requests, and "cassandra_flags"
- Uses structured schema for consistent output format

**Stage 3: GeneratorAgent (`carlos.py:129-158`)**
- Translates analytical insights into natural language responses  
- Supports both streaming and complete response generation
- Uses thinker context and timestamp for response generation

**Stage 4: SummarizerAgent (`carlos.py:160-174`)**
- Creates summaries and tags for both user messages and responses
- Enables semantic search and memory organization

### Database Architecture (MongoDB)

**CarlosDatabaseHandler (`carlos.py:177-425`)**

**Core Collections:**
- `messages`: User messages with summaries, tags, embeddings, timestamps
- `responses`: Agent responses with same structure as messages  
- `analyses`: Thinker analysis data
- `insights`: Autonomous thoughts and insights
- `interactions`: Full interaction logs linking messages, responses, analyses
- `cassandra_flags`: Flags raised during thinking for monitoring

**Key Features:**
- Vector similarity search with manual cosine similarity calculation (MongoDB Atlas not required)
- Tag-based search for fast retrieval
- Automatic indexing on tags and timestamps
- Custom JSON encoder for MongoDB ObjectId and datetime handling

### Configuration

**Environment Variables:**
- `LMSTUDIO_URL`: Chat completions endpoint (default: http://localhost:1234)
- `MONGODB_URI`: Database connection (default: mongodb://localhost:27017)  
- `EMBEDDINGS_MODEL`: Embedding model (default: text-embedding-nomic-embed-text-v1.5)

**API Endpoints (`app.py`):**
- `GET /`: Main chat interface (FastAPI/Jinja2 templates)
- `GET /stream`: Streaming response endpoint with event-source
- `GET /favicon.ico`: Favicon serving endpoint
- Single Carlos instance per application initialized with test_user

### Key Implementation Details

**Async Pipeline Processing:**
- All agent operations are async with httpx clients
- Streaming responses use async generators
- Database operations are synchronous (PyMongo)
- Proper resource cleanup with `close()` methods

**Memory Management:**
- Message chunking for inputs >4000 characters
- Separate storage of chunks with individual summaries
- Vector embeddings for semantic similarity search
- Interaction tracking with full context preservation

**Error Handling:**
- Graceful fallbacks when embeddings unavailable
- HTTP error handling with proper logging
- MongoDB connection error management
- JSON parsing fallbacks for non-structured responses

## File Structure

**Core Implementation:**
- `carlos.py`: Main AI pipeline with LlmAgent classes and multi-agent architecture
- `app.py`: FastAPI web server with streaming endpoint and template rendering
- `requirements.txt`: Python dependencies (flask, pymongo, httpx, requests)
- `reset_db.py`: Database management utility with user-specific and bulk operations

**Configuration Files:**
- `prompts/`: System prompts for each agent (curator, thinker, response_generator, summarizer)  
- `schemas/`: JSON schemas defining expected outputs for each agent
- `docker-compose.yml`: MongoDB container setup

**Web Interface:**
- `templates/index.html`: Chat interface with EventSource streaming support
- `templates/login.html`: User login interface
- `static/styles.css`: Application styling
- `static/images/`: Assets including carlos_logo.png and favicon.png

**Development Tools:**
- `reset_db.py`: Database management script with user-specific resets
- `docs/ArchitechturePlans.md`: Comprehensive theoretical framework and "Shards of Thought" cognitive architecture analysis

## Development Notes

**Schema-Driven Design:**
All agents use JSON schemas to ensure consistent, structured outputs that can be reliably processed by the pipeline.

**Modular Agent System:**
Each agent (Curator, Thinker, Generator, Summarizer) is a separate class inheriting from `LlmAgent` base class, making the system extensible.

**Context-Aware Processing:**
The thinker agent performs iterative reasoning until it determines sufficient context exists, preventing shallow responses.

**User-Specific Databases:**
Each user gets their own MongoDB database (`carlos_{username}`) enabling personalized memory and context.

**Framework Evolution:**
The architecture implements a "Recursive Shard Architecture" solving the stability-plasticity dilemma by separating:
- Plasticity (Database): Factual, semantic, episodic memory - allows continuous learning
- Stability (Network): Procedural, conceptual knowledge - maintains stable reasoning patterns

**LlmAgent Base Class:**
All agents inherit from `LlmAgent` providing consistent async HTTP client patterns with httpx, schema-driven JSON responses, and streaming support.