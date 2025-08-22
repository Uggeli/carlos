# Carlos Chat

A minimal Flask + Jinja2 chat UI wired to the Carlos pipeline.

## Run locally

1) Create a virtual environment (optional) and install deps

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2) Ensure LM Studio (or your chat completions service) is reachable at `LMSTUDIO_URL` (defaults to http://localhost:1234/v1/chat/completions). Optionally set `MONGODB_URI` if you want persistence.

Vector Search (optional but recommended):
- Provide an embeddings endpoint via `EMBEDDINGS_URL` (OpenAI-compatible `/v1/embeddings`).
- Choose an embeddings model via `EMBEDDINGS_MODEL` (e.g., `nomic-embed-text`).
- If `EMBEDDINGS_URL` is not set, Carlos will try deriving `/v1/embeddings` from `LMSTUDIO_URL`.
- When enabled, Carlos stores an `embedding` array on new `messages` (and opportunistically on `events`/`entities` if they have text fields), and performs a top-k cosine similarity search to surface `retrieved_context.vector_matches` alongside traditional queries.

3) Start the app

```powershell
$env:FLASK_APP = "app.py"; $env:FLASK_ENV = "development"; python app.py
```

Open http://127.0.0.1:5000/

## Notes
- The API endpoint is POST /api/chat with JSON `{ "message": "..." }`.
- Responses include Bark TTS tags in the text, as produced by Carlos.
- Debugging: `Carlos.index_health()` shows Mongo indexes; vector matches appear in the assembled context when embeddings are available.
