"""
conftest.py — shared pytest fixtures for the RAG chatbot test suite.

Adds the backend/ directory to sys.path so all backend modules are importable
without a package installation step, and provides reusable fixtures for mocking
and test data setup.
"""
import sys
import os
from unittest.mock import MagicMock, patch
import pytest

# Insert the backend directory (parent of this file) at the front of sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Mock response helpers — mimic the Anthropic SDK content block structure
# ---------------------------------------------------------------------------

class MockTextBlock:
    """Mimics anthropic.types.TextBlock for test responses."""
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class MockToolUseBlock:
    """Mimics anthropic.types.ToolUseBlock for test responses."""
    def __init__(self, name: str, input_data: dict, tool_use_id: str = "tu_test123"):
        self.type = "tool_use"
        self.name = name
        self.input = input_data
        self.id = tool_use_id


class MockAnthropicResponse:
    """Mimics the top-level Anthropic Messages API response object."""
    def __init__(self, content: list, stop_reason: str = "end_turn"):
        self.content = content
        self.stop_reason = stop_reason


# ---------------------------------------------------------------------------
# RAGSystem mock fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag_system():
    """
    Returns a MagicMock RAGSystem with sensible defaults for API endpoint tests.

    The mock pre-configures:
    - query()  → ("Test answer about the course.", [])
    - get_course_analytics() → {"total_courses": 2, "course_titles": [...]}
    - session_manager.create_session() → "test-session-id"
    - session_manager.clear_session() → None
    """
    rag = MagicMock()
    rag.query.return_value = ("Test answer about the course.", [])
    rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Intro to ML", "Advanced NLP"],
    }
    rag.session_manager.create_session.return_value = "test-session-id"
    rag.session_manager.clear_session.return_value = None
    return rag


# ---------------------------------------------------------------------------
# FastAPI TestClient fixture — isolates the app from the real RAGSystem and
# the static-file mount that expects ../frontend/ to exist on disk.
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app(mock_rag_system):
    """
    Creates a clean FastAPI test application that mirrors the production
    endpoints without importing backend/app.py directly (which would trigger
    RAGSystem initialisation and the static-file mount at import time).

    Each endpoint delegates to `mock_rag_system`, so tests exercise the full
    HTTP layer (routing, Pydantic validation, status codes, JSON shape) while
    remaining fast and deterministic.
    """
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from typing import List, Optional

    test_fastapi_app = FastAPI(title="RAG System — Test App")

    test_fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Pydantic models (mirrors app.py) ---------------------------------

    class QueryRequest(BaseModel):
        query: str
        session_id: Optional[str] = None

    class SourceItem(BaseModel):
        label: str
        lesson_link: Optional[str] = None

    class QueryResponse(BaseModel):
        answer: str
        sources: List[SourceItem]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: List[str]

    # ---- Endpoints --------------------------------------------------------

    @test_fastapi_app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag_system.session_manager.create_session()
            answer, sources = mock_rag_system.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @test_fastapi_app.delete("/api/session/{session_id}")
    async def delete_session(session_id: str):
        try:
            mock_rag_system.session_manager.clear_session(session_id)
            return {"success": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @test_fastapi_app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return test_fastapi_app


@pytest.fixture
def client(test_app):
    """
    Returns a FastAPI TestClient bound to the isolated test application.
    Requires httpx to be installed (included in dev dependencies).
    """
    from fastapi.testclient import TestClient
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# Reusable sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_query_payload():
    """Minimal valid JSON body for POST /api/query."""
    return {"query": "What topics are covered in the ML course?"}


@pytest.fixture
def sample_query_with_session():
    """Valid JSON body for POST /api/query with an existing session_id."""
    return {
        "query": "Tell me about lesson 2.",
        "session_id": "existing-session-abc",
    }


@pytest.fixture
def sample_sources():
    """A realistic list of SourceItem dicts as returned by the RAG system."""
    return [
        {"label": "Intro to ML — Lesson 1", "lesson_link": "https://example.com/lesson1"},
        {"label": "Intro to ML — Lesson 2", "lesson_link": None},
    ]
