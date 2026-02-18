"""
Tests for RAGSystem content-query handling in backend/rag_system.py.

Suite A — unit tests with mocked AI (fast, no I/O beyond ChromaDB).
Suite B — integration tests using a real VectorStore to expose the
          MAX_RESULTS=0 bug in config.py.
"""
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from vector_store import VectorStore, SearchResults
from rag_system import RAGSystem
from models import Course, Lesson, CourseChunk

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Config stubs
# ---------------------------------------------------------------------------

@dataclass
class _GoodConfig:
    """Correct configuration — mirrors what config.py SHOULD have."""
    ANTHROPIC_API_KEY: str = "test-key"
    ANTHROPIC_MODEL: str = "claude-test-model"
    EMBEDDING_MODEL: str = EMBEDDING_MODEL
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100
    MAX_RESULTS: int = 5        # CORRECT
    MAX_HISTORY: int = 2
    CHROMA_PATH: str = "./chroma_db"


@dataclass
class _BrokenConfig(_GoodConfig):
    """Broken configuration — replicates the MAX_RESULTS=0 bug in config.py."""
    MAX_RESULTS: int = 0        # BUG: zero results returned on every search


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _seed_store(store: VectorStore) -> None:
    """Insert a minimal course + one content chunk into *store*."""
    course = Course(
        title="Intro to Python",
        course_link="https://example.com/python",
        lessons=[
            Lesson(
                lesson_number=1,
                title="Variables",
                lesson_link="https://example.com/python/1",
            )
        ],
    )
    store.add_course_metadata(course)
    store.add_course_content(
        [
            CourseChunk(
                content="Lesson 1 content: Variables store data in Python.",
                course_title="Intro to Python",
                lesson_number=1,
                chunk_index=0,
            )
        ]
    )


# ---------------------------------------------------------------------------
# Suite A — unit tests (mocked AIGenerator)
# ---------------------------------------------------------------------------

class TestRAGSystemUnit:

    @pytest.fixture
    def rag(self, tmp_path):
        """RAGSystem with a mocked AIGenerator and real (empty) VectorStore."""
        cfg = _GoodConfig(CHROMA_PATH=str(tmp_path / "chroma"))
        with patch("rag_system.AIGenerator") as MockAI:
            MockAI.return_value.generate_response.return_value = "Mocked answer."
            system = RAGSystem(cfg)
        return system

    def test_query_returns_non_empty_answer(self, rag):
        """query() must return a non-empty string answer."""
        rag.ai_generator.generate_response.return_value = "Some answer."
        answer, _ = rag.query("What is Python?")
        assert isinstance(answer, str) and len(answer) > 0

    def test_query_returns_sources_as_list(self, rag):
        """query() must return sources as a list (possibly empty)."""
        rag.ai_generator.generate_response.return_value = "Answer."
        _, sources = rag.query("What is Python?")
        assert isinstance(sources, list)

    def test_sources_reset_after_every_query(self, rag):
        """tool_manager.reset_sources() must be called after each query."""
        rag.ai_generator.generate_response.return_value = "Answer."
        rag.tool_manager.reset_sources = MagicMock()
        rag.query("test query")
        rag.tool_manager.reset_sources.assert_called_once()

    def test_session_history_updated_after_query(self, rag):
        """The user question and AI answer must be saved to the session."""
        rag.ai_generator.generate_response.return_value = "Answer."
        session_id = rag.session_manager.create_session()
        rag.query("What are variables?", session_id=session_id)
        history = rag.session_manager.get_conversation_history(session_id)
        assert history is not None
        assert "What are variables?" in history

    def test_tool_definitions_passed_to_ai_generator(self, rag):
        """generate_response() must receive the registered tool definitions."""
        rag.ai_generator.generate_response.return_value = "Answer."
        rag.query("test")
        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert "tools" in call_kwargs
        tool_names = [t["name"] for t in call_kwargs["tools"]]
        assert "search_course_content" in tool_names


# ---------------------------------------------------------------------------
# Suite B — integration tests (real VectorStore, exposes the config bug)
# ---------------------------------------------------------------------------

class TestRAGSystemSearchIntegration:
    """
    These tests do NOT mock the VectorStore so they exercise the real search
    path.  They will reveal that MAX_RESULTS=0 (config.py line 21) prevents
    any content from being retrieved.
    """

    @pytest.fixture
    def store_broken(self, tmp_path):
        """Seeded VectorStore with max_results=0 — replicates the production bug."""
        store = VectorStore(
            chroma_path=str(tmp_path / "chroma_broken"),
            embedding_model=EMBEDDING_MODEL,
            max_results=0,
        )
        _seed_store(store)
        return store

    @pytest.fixture
    def store_fixed(self, tmp_path):
        """Seeded VectorStore with max_results=5 — the corrected configuration."""
        store = VectorStore(
            chroma_path=str(tmp_path / "chroma_fixed"),
            embedding_model=EMBEDDING_MODEL,
            max_results=5,
        )
        _seed_store(store)
        return store

    def test_search_returns_empty_with_max_results_zero(self, store_broken):
        """
        BUG EXPOSURE: VectorStore.search() returns no documents when
        max_results=0, even though data has been seeded.

        Root cause: config.py line 21 sets MAX_RESULTS = 0.
        Fix: change MAX_RESULTS to 5.

        This test is EXPECTED TO FAIL on the current codebase.
        """
        results = store_broken.search(query="Python variables")
        # Either ChromaDB raises (caught → error result) or returns 0 docs.
        # Either way, the actual document must not be present.
        assert results.is_empty(), (
            "Expected no results because max_results=0, but documents were returned. "
            "If this assertion fails, the bug may already be fixed."
        )

    def test_search_returns_content_with_max_results_five(self, store_fixed):
        """
        With max_results=5, the seeded content must be retrieved.

        This test confirms that the fix (MAX_RESULTS=5) resolves the bug.
        """
        results = store_fixed.search(query="Python variables")
        assert not results.is_empty(), (
            "Expected content to be returned with max_results=5, but got none."
        )
        assert any("Python" in doc for doc in results.documents)

    def test_course_search_tool_returns_no_content_when_max_results_zero(self, store_broken):
        """
        End-to-end: CourseSearchTool.execute() must not return course content
        when the underlying store has max_results=0.

        This test is EXPECTED TO FAIL on the current codebase.
        """
        from search_tools import CourseSearchTool
        tool = CourseSearchTool(store_broken)
        result = tool.execute(query="Python variables")

        # Should be an error or no-results message — NOT the actual document text.
        assert "Variables store data in Python" not in result, (
            "CourseSearchTool returned actual content despite max_results=0. "
            "The bug may already be fixed."
        )

    def test_course_search_tool_returns_content_when_max_results_five(self, store_fixed):
        """
        End-to-end: CourseSearchTool.execute() should return course content
        when max_results=5.
        """
        from search_tools import CourseSearchTool
        tool = CourseSearchTool(store_fixed)
        result = tool.execute(query="Python variables")

        assert "Intro to Python" in result, (
            "Expected course title in result but got: " + result
        )
