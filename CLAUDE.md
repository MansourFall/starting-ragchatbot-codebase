# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Install dependencies:**
```bash
uv sync
```

**Run the server** (from repo root):
```bash
./run.sh
# or manually:
cd backend && uv run uvicorn app:app --reload --port 8000
```

Server runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

**Environment setup:** Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

There are no tests or linting configurations in this project.

## Architecture

This is a RAG (Retrieval-Augmented Generation) chatbot. All backend code lives in `backend/` and is run from that directory — imports are relative to `backend/` with no package structure.

### Request flow
1. `frontend/script.js` — sends `POST /api/query` with `{query, session_id}`
2. `backend/app.py` — FastAPI entry point; creates session if none, delegates to `RAGSystem.query()`
3. `backend/rag_system.py` — orchestrates all components; fetches conversation history, calls `AIGenerator`
4. `backend/ai_generator.py` — makes first Claude API call with the `search_course_content` tool available
5. If Claude invokes the tool → `backend/search_tools.py` → `backend/vector_store.py` → ChromaDB semantic search
6. Second Claude call synthesizes the final answer from retrieved chunks
7. Exchange is saved to `SessionManager`; `{answer, sources, session_id}` returned to frontend

### Key design decisions
- **Tool-based RAG**: Claude decides whether to search (max one search per query). There is no pre-retrieval step — context is only injected if Claude calls the tool.
- **Conversation history** is injected into the system prompt as plain text (not as additional messages). Capped at 2 exchanges (4 messages) per session. Sessions are in-memory only.
- **Two ChromaDB collections**: `course_catalog` (course metadata for semantic name resolution) and `course_content` (chunked text with embeddings).
- **Embedding model**: `all-MiniLM-L6-v2` via Sentence Transformers runs locally.
- **Duplicate prevention**: On startup, `add_course_folder()` fetches existing course titles from ChromaDB and skips already-ingested files.

### Document format expected by `DocumentProcessor`
Course `.txt` files in `docs/` must follow:
```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 0: <title>
Lesson Link: <url>
<lesson content...>

Lesson 1: <title>
...
```
Chunks are sentence-aware, 800 chars with 100-char overlap. The first chunk of each lesson is prefixed with `"Lesson N content: ..."`.

### Configuration (`backend/config.py`)
All tunable constants live in the `Config` dataclass and are imported as a singleton `config`. Key values: `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`, `MAX_RESULTS=5`, `MAX_HISTORY=2`, `ANTHROPIC_MODEL="claude-sonnet-4-20250514"`.
- always use 'uv' to manage all dependencies or run code
- use uv to run Python files