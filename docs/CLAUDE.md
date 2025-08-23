# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```powershell
# Install dependencies in virtual environment
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt

# Start Flask development server
$env:FLASK_APP = "app.py"; $env:FLASK_ENV = "development"; python app.py
```

### Database Setup
```powershell
# Start MongoDB using Docker Compose
docker-compose up -d

# MongoDB will be available at localhost:27017
```

### Testing
- No formal test framework is configured
- Use `carlos_playground.ipynb` for interactive testing
- Use `tts_tests.ipynb` for TTS-related testing

## Architecture Overview

### Theoretical Foundation: "Shards of Thought" Framework

Carlos implements a **Recursive Shard Architecture** that solves the stability-plasticity dilemma through architectural separation:

- **Plasticity (Database)**: Factual, semantic, and episodic memory stored in MongoDB - infinitely plastic, allows constant learning without forgetting
- **Stability (Network)**: Procedural and conceptual knowledge in model weights - stable reasoning patterns and "how to think"

This prevents catastrophic forgetting while enabling continuous learning.

### The Recursive Shard Pipeline

**Stage I: Curator (The Investigator 🕵️‍♀️)**
- Perception and information gathering mechanism
- Assesses information needs and queries external memory
- Constructs fresh, bespoke context for each interaction
- Example output in `CuratorOutputs.md` shows investigation queries with priorities

**Stage II: Thinker (The Strategist 🧠)**  
- Cognitive core performing deep analytical reasoning
- Uses internal dialogue: "Let me think through this...", "What do I actually know vs assume?"
- Grounds analysis in facts vs assumptions, identifies patterns and gaps
- Produces structured response blueprint with verified facts and guidance
- System prompt available in `Thinker Model System Prompt.md`

**Stage III: Response Generator (The Communicator)**
- Translates analytical blueprint into natural, empathetic language
- Applies Bark TTS formatting for speech synthesis
- Executes the cognitive plan from the Thinker

**Flask Web Interface (`app.py`)**
- Minimal web server with chat UI
- Single endpoint: `POST /api/chat` 
- Serves static chat interface at `/`

### Future Evolution: Hopfield Transformer

The architecture is designed to evolve toward a **Hopfield Transformer** that replaces static attention with dynamic associative memories:
- **Updatability**: New concepts can be added directly to Hopfield layers
- **Efficiency**: One-shot updates vs expensive retraining
- **Cognitive Authenticity**: Actively assimilates knowledge like biological brains

### Data Storage (MongoDB)

**Collections:**
- `messages`: Chat history with embeddings for vector search
- `analyses`: Curator/thinker outputs by type and topic
- `contexts`: Assembled context objects
- `entities`: Extracted entities from conversations
- `events`: Timeline events with related entities
- `user_state`: User goals and active projects

**Indexing Strategy:**
- User+timestamp indexes for efficient retrieval
- Text indexes for content search
- Topic-based partitioning for context organization

### Configuration

**Environment Variables:**
- `LMSTUDIO_URL`: Chat completions endpoint (default: http://localhost:1234/v1/chat/completions)
- `MONGODB_URI`: Database connection (default: mongodb://localhost:27017/carlos)
- `EMBEDDINGS_URL`: Vector embeddings endpoint (optional)
- `EMBEDDINGS_MODEL`: Embedding model name (default: nomic-embed-text)
- `PORT`: Flask server port (default: 5000)

### Key Features

**Vector Search:**
- Automatic embedding generation for searchable content
- Cosine similarity search for context retrieval
- Falls back gracefully when embeddings unavailable

**Bark TTS Integration:**
- Response formatting with emotional markers: `[laughter]`, `[sighs]`, `[gasps]`
- Emphasis through CAPITALIZATION
- Natural pause indicators with `...`
- Music notation with `♪`

**Context Management:**
- Smart context assembly based on curator analysis
- Minimal context mode for standalone queries
- Topic-based conversation threading
- Memory consolidation and pruning

## File Structure

**Core Implementation:**
- `carlos.py`: Core AI pipeline implementing the Recursive Shard Architecture
- `app.py`: Flask web server and API endpoints
- `templates/chat.html`: Chat interface with dark theme
- `requirements.txt`: Python dependencies (Flask, PyMongo, requests)
- `docker-compose.yml`: MongoDB container setup

**Documentation:**
- `ArchitechturePlans.md`: Detailed analysis of the "Shards of Thought" framework and Hopfield Transformer evolution
- `Thinker Model System Prompt.md`: System prompt defining the Thinker's analytical reasoning process
- `CuratorOutputs.md`: Example curator output showing investigation queries and priorities
- `README.md`: Basic setup and running instructions

**Development/Testing:**
- `carlos_playground.ipynb`: Interactive testing notebook
- `tts_tests.ipynb`: TTS-related testing
- `carlos_response.wav`: Sample TTS output