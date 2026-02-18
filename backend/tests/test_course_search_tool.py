"""
Tests for CourseSearchTool.execute() in backend/search_tools.py.

Suite A — unit tests using a mocked VectorStore (fast, no I/O).
Suite B — integration tests using a real VectorStore backed by a
          temporary ChromaDB instance.  These tests expose the
          MAX_RESULTS=0 bug present in config.py.
"""
import pytest
from unittest.mock import MagicMock

from vector_store import VectorStore, SearchResults
from search_tools import CourseSearchTool
from models import Course, Lesson, CourseChunk

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    """Return a MagicMock that passes isinstance(x, VectorStore) checks."""
    return MagicMock(spec=VectorStore)


@pytest.fixture
def search_tool(mock_store):
    return CourseSearchTool(mock_store)


# ---------------------------------------------------------------------------
# Suite A — unit tests (mocked VectorStore)
# ---------------------------------------------------------------------------

class TestCourseSearchToolUnit:

    def test_execute_formats_results_with_course_and_lesson(self, search_tool, mock_store):
        """Results should include the course title and lesson number as a header."""
        mock_store.search.return_value = SearchResults(
            documents=["Python is a dynamically-typed language."],
            metadata=[{"course_title": "AI Basics", "lesson_number": 1}],
            distances=[0.2],
        )
        mock_store.get_lesson_link.return_value = "https://example.com/lesson/1"

        result = search_tool.execute(query="What is Python?")

        assert "AI Basics" in result
        assert "Lesson 1" in result
        assert "Python is a dynamically-typed language." in result

    def test_execute_no_results_returns_friendly_message(self, search_tool, mock_store):
        """Empty result set should produce a 'No relevant content found' message."""
        mock_store.search.return_value = SearchResults(
            documents=[], metadata=[], distances=[]
        )

        result = search_tool.execute(query="completely unknown topic")

        assert "No relevant content found" in result

    def test_execute_error_is_surfaced_to_caller(self, search_tool, mock_store):
        """If the store returns an error, execute() should return that error text."""
        mock_store.search.return_value = SearchResults.empty("Search error: connection failed")

        result = search_tool.execute(query="anything")

        assert "Search error" in result

    def test_execute_passes_course_name_to_store(self, search_tool, mock_store):
        """course_name parameter must be forwarded to VectorStore.search()."""
        mock_store.search.return_value = SearchResults(documents=[], metadata=[], distances=[])

        search_tool.execute(query="transformers", course_name="Deep Learning")

        mock_store.search.assert_called_once_with(
            query="transformers",
            course_name="Deep Learning",
            lesson_number=None,
        )

    def test_execute_passes_lesson_number_to_store(self, search_tool, mock_store):
        """lesson_number parameter must be forwarded to VectorStore.search()."""
        mock_store.search.return_value = SearchResults(documents=[], metadata=[], distances=[])

        search_tool.execute(query="attention mechanism", lesson_number=3)

        mock_store.search.assert_called_once_with(
            query="attention mechanism",
            course_name=None,
            lesson_number=3,
        )

    def test_last_sources_populated_after_successful_search(self, search_tool, mock_store):
        """last_sources should contain one entry per result for the UI."""
        mock_store.search.return_value = SearchResults(
            documents=["content here"],
            metadata=[{"course_title": "ML Course", "lesson_number": 2}],
            distances=[0.1],
        )
        mock_store.get_lesson_link.return_value = "https://example.com/lesson/2"

        search_tool.execute(query="gradient descent")

        assert len(search_tool.last_sources) == 1
        assert search_tool.last_sources[0]["label"] == "ML Course - Lesson 2"

    def test_no_results_message_includes_filter_context(self, search_tool, mock_store):
        """When course/lesson filters are used, they should appear in the no-results text."""
        mock_store.search.return_value = SearchResults(documents=[], metadata=[], distances=[])

        result = search_tool.execute(
            query="anything", course_name="Python 101", lesson_number=2
        )

        assert "Python 101" in result
        assert "2" in result


# ---------------------------------------------------------------------------
# Suite B — integration tests (real VectorStore, exposes MAX_RESULTS=0 bug)
# ---------------------------------------------------------------------------

def _seed_store(store: VectorStore) -> None:
    """Insert one course with one lesson chunk into the given store."""
    course = Course(
        title="Test Course",
        course_link="https://example.com/course",
        lessons=[
            Lesson(
                lesson_number=1,
                title="Intro",
                lesson_link="https://example.com/lesson/1",
            )
        ],
    )
    store.add_course_metadata(course)
    store.add_course_content(
        [
            CourseChunk(
                content="Lesson 1 content: Python variables store data.",
                course_title="Test Course",
                lesson_number=1,
                chunk_index=0,
            )
        ]
    )


class TestCourseSearchToolIntegration:

    @pytest.fixture
    def store_zero_results(self, tmp_path):
        """Real VectorStore with max_results=0 — replicates the config.py bug."""
        store = VectorStore(
            chroma_path=str(tmp_path / "chroma_zero"),
            embedding_model=EMBEDDING_MODEL,
            max_results=0,
        )
        _seed_store(store)
        return store

    @pytest.fixture
    def store_valid(self, tmp_path):
        """Real VectorStore with max_results=5 — the correct configuration."""
        store = VectorStore(
            chroma_path=str(tmp_path / "chroma_valid"),
            embedding_model=EMBEDDING_MODEL,
            max_results=5,
        )
        _seed_store(store)
        return store

    def test_max_results_zero_tool_returns_no_content(self, store_zero_results):
        """
        BUG EXPOSURE: When MAX_RESULTS=0 (as in config.py), the tool returns
        no course content even though data exists in the vector store.

        This test is EXPECTED TO FAIL until config.py is fixed.
        Fix: change MAX_RESULTS from 0 to 5 in backend/config.py.
        """
        tool = CourseSearchTool(store_zero_results)
        result = tool.execute(query="Python variables")

        # With max_results=0 the store either raises (caught as "Search error")
        # or returns 0 docs ("No relevant content found") — in both cases the
        # actual document text must NOT appear in the output.
        assert "Python variables store data" not in result, (
            "Actual content was returned despite MAX_RESULTS=0. "
            "The bug may already be fixed."
        )

    def test_max_results_five_tool_returns_content(self, store_valid):
        """
        With MAX_RESULTS=5 the tool should return the seeded document content.

        This test confirms that changing MAX_RESULTS to 5 resolves the bug.
        """
        tool = CourseSearchTool(store_valid)
        result = tool.execute(query="Python variables")

        assert "No relevant content found" not in result
        assert "Test Course" in result
