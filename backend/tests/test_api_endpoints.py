"""
test_api_endpoints.py — HTTP-layer tests for the RAG chatbot API.

All tests use the isolated `client` fixture from conftest.py, which wires up a
clean FastAPI application that mirrors the production endpoints in app.py but
delegates every call to `mock_rag_system` instead of the real RAGSystem.  This
means:

- No ChromaDB is created.
- No Anthropic API calls are made.
- The static-file mount (which requires ../frontend/ on disk) is absent.
- Tests run quickly and deterministically.

Test suites
-----------
TestQueryEndpoint       — POST /api/query
TestCoursesEndpoint     — GET  /api/courses
TestDeleteSessionEndpoint — DELETE /api/session/{session_id}
"""

from unittest.mock import MagicMock
import pytest


# ===========================================================================
# POST /api/query
# ===========================================================================

class TestQueryEndpoint:
    """Tests for the POST /api/query endpoint."""

    def test_returns_200_on_valid_request(self, client, sample_query_payload):
        """A well-formed request must return HTTP 200."""
        response = client.post("/api/query", json=sample_query_payload)
        assert response.status_code == 200

    def test_response_contains_answer_field(self, client, sample_query_payload):
        """Response JSON must include a non-empty 'answer' string."""
        response = client.post("/api/query", json=sample_query_payload)
        body = response.json()
        assert "answer" in body
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_response_contains_sources_list(self, client, sample_query_payload):
        """Response JSON must include a 'sources' key whose value is a list."""
        response = client.post("/api/query", json=sample_query_payload)
        body = response.json()
        assert "sources" in body
        assert isinstance(body["sources"], list)

    def test_response_contains_session_id(self, client, sample_query_payload):
        """Response JSON must include a non-empty 'session_id' string."""
        response = client.post("/api/query", json=sample_query_payload)
        body = response.json()
        assert "session_id" in body
        assert isinstance(body["session_id"], str)
        assert len(body["session_id"]) > 0

    def test_new_session_created_when_none_provided(self, client, mock_rag_system, sample_query_payload):
        """When no session_id is sent, session_manager.create_session() must be called."""
        client.post("/api/query", json=sample_query_payload)
        mock_rag_system.session_manager.create_session.assert_called_once()

    def test_existing_session_not_recreated(self, client, mock_rag_system, sample_query_with_session):
        """When a session_id is provided, create_session() must NOT be called."""
        client.post("/api/query", json=sample_query_with_session)
        mock_rag_system.session_manager.create_session.assert_not_called()

    def test_existing_session_id_echoed_in_response(self, client, sample_query_with_session):
        """The response session_id must match the one sent in the request."""
        response = client.post("/api/query", json=sample_query_with_session)
        body = response.json()
        assert body["session_id"] == sample_query_with_session["session_id"]

    def test_rag_query_called_with_correct_query_text(self, client, mock_rag_system, sample_query_payload):
        """rag_system.query() must receive the exact query string from the request body."""
        client.post("/api/query", json=sample_query_payload)
        call_args = mock_rag_system.query.call_args
        assert call_args[0][0] == sample_query_payload["query"]

    def test_missing_query_field_returns_422(self, client):
        """A request body without the required 'query' field must return HTTP 422."""
        response = client.post("/api/query", json={})
        assert response.status_code == 422

    def test_empty_query_string_is_accepted(self, client):
        """An empty string for 'query' is technically valid JSON — must return 200."""
        response = client.post("/api/query", json={"query": ""})
        assert response.status_code == 200

    def test_sources_reflected_in_response(self, client, mock_rag_system, sample_sources, sample_query_payload):
        """When rag_system.query() returns sources, they must appear in the response."""
        mock_rag_system.query.return_value = ("Some answer.", sample_sources)
        response = client.post("/api/query", json=sample_query_payload)
        body = response.json()
        assert len(body["sources"]) == len(sample_sources)
        assert body["sources"][0]["label"] == sample_sources[0]["label"]

    def test_rag_exception_returns_500(self, client, mock_rag_system, sample_query_payload):
        """If rag_system.query() raises, the endpoint must return HTTP 500."""
        mock_rag_system.query.side_effect = RuntimeError("vector store unavailable")
        response = client.post("/api/query", json=sample_query_payload)
        assert response.status_code == 500

    def test_500_response_includes_detail_message(self, client, mock_rag_system, sample_query_payload):
        """A 500 error response must include the exception message in 'detail'."""
        error_msg = "vector store unavailable"
        mock_rag_system.query.side_effect = RuntimeError(error_msg)
        response = client.post("/api/query", json=sample_query_payload)
        assert error_msg in response.json()["detail"]


# ===========================================================================
# GET /api/courses
# ===========================================================================

class TestCoursesEndpoint:
    """Tests for the GET /api/courses endpoint."""

    def test_returns_200(self, client):
        """GET /api/courses must return HTTP 200."""
        response = client.get("/api/courses")
        assert response.status_code == 200

    def test_response_contains_total_courses(self, client):
        """Response JSON must include an integer 'total_courses' field."""
        response = client.get("/api/courses")
        body = response.json()
        assert "total_courses" in body
        assert isinstance(body["total_courses"], int)

    def test_response_contains_course_titles_list(self, client):
        """Response JSON must include a list of course title strings."""
        response = client.get("/api/courses")
        body = response.json()
        assert "course_titles" in body
        assert isinstance(body["course_titles"], list)

    def test_total_courses_matches_titles_length(self, client):
        """'total_courses' must equal the number of items in 'course_titles'."""
        response = client.get("/api/courses")
        body = response.json()
        assert body["total_courses"] == len(body["course_titles"])

    def test_course_titles_are_strings(self, client):
        """Every entry in 'course_titles' must be a string."""
        response = client.get("/api/courses")
        body = response.json()
        for title in body["course_titles"]:
            assert isinstance(title, str)

    def test_analytics_method_called(self, client, mock_rag_system):
        """get_course_analytics() must be invoked exactly once per request."""
        client.get("/api/courses")
        mock_rag_system.get_course_analytics.assert_called_once()

    def test_get_courses_exception_returns_500(self, client, mock_rag_system):
        """If get_course_analytics() raises, the endpoint must return HTTP 500."""
        mock_rag_system.get_course_analytics.side_effect = RuntimeError("db error")
        response = client.get("/api/courses")
        assert response.status_code == 500

    def test_empty_catalog_returns_zero_courses(self, client, mock_rag_system):
        """An empty course catalog must be represented as total_courses=0 and []."""
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": [],
        }
        response = client.get("/api/courses")
        body = response.json()
        assert body["total_courses"] == 0
        assert body["course_titles"] == []


# ===========================================================================
# DELETE /api/session/{session_id}
# ===========================================================================

class TestDeleteSessionEndpoint:
    """Tests for the DELETE /api/session/{session_id} endpoint."""

    def test_returns_200_on_valid_session(self, client):
        """Deleting an existing session must return HTTP 200."""
        response = client.delete("/api/session/test-session-id")
        assert response.status_code == 200

    def test_response_contains_success_true(self, client):
        """Response body must be {'success': True}."""
        response = client.delete("/api/session/test-session-id")
        assert response.json() == {"success": True}

    def test_clear_session_called_with_correct_id(self, client, mock_rag_system):
        """session_manager.clear_session() must be called with the URL path session_id."""
        session_id = "abc-123"
        client.delete(f"/api/session/{session_id}")
        mock_rag_system.session_manager.clear_session.assert_called_once_with(session_id)

    def test_clear_session_exception_returns_500(self, client, mock_rag_system):
        """If clear_session() raises, the endpoint must return HTTP 500."""
        mock_rag_system.session_manager.clear_session.side_effect = RuntimeError("session not found")
        response = client.delete("/api/session/bad-id")
        assert response.status_code == 500
