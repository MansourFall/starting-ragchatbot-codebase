# Frontend-Facing API Testing Changes

This document records the testing-infrastructure additions made to validate the
HTTP API that the frontend (`frontend/script.js`) depends on.

---

## What changed

### 1. `pyproject.toml` — pytest configuration + new dev dependency

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "httpx>=0.28.0",      # required by FastAPI TestClient
]

[tool.pytest.ini_options]
testpaths = ["backend/tests"]
pythonpath = ["backend"]
addopts  = "-v --tb=short"
filterwarnings = [
    "ignore::DeprecationWarning",
    "ignore::UserWarning",
]
```

- `httpx` is the async HTTP transport that FastAPI's `TestClient` requires.
- `pytest.ini_options` removes the need to pass flags on every `uv run pytest`
  invocation and ensures the `backend/` directory is on `PYTHONPATH` so all
  backend modules resolve correctly.

---

### 2. `backend/tests/conftest.py` — shared fixtures

Added four categories of shared fixture:

| Fixture | Purpose |
|---|---|
| `MockTextBlock` / `MockToolUseBlock` / `MockAnthropicResponse` | Helper classes that mimic Anthropic SDK response objects (reusable across all test modules). |
| `mock_rag_system` | `MagicMock` of `RAGSystem` with sensible defaults; avoids ChromaDB/Anthropic I/O. |
| `test_app` | Isolated FastAPI app that mirrors the production endpoints from `app.py` but delegates to `mock_rag_system`. Avoids the `StaticFiles` mount that requires `../frontend/` to exist on disk. |
| `client` | `fastapi.testclient.TestClient` bound to `test_app`. |
| `sample_query_payload` / `sample_query_with_session` / `sample_sources` | Reusable request/response data fixtures. |

---

### 3. `backend/tests/test_api_endpoints.py` — API endpoint test suite (new file)

Tests the three endpoints that `frontend/script.js` calls:

#### `POST /api/query` — 13 tests (`TestQueryEndpoint`)

| Test | What it validates |
|---|---|
| `test_returns_200_on_valid_request` | HTTP 200 on a well-formed body |
| `test_response_contains_answer_field` | `answer` is a non-empty string |
| `test_response_contains_sources_list` | `sources` is a list |
| `test_response_contains_session_id` | `session_id` is a non-empty string |
| `test_new_session_created_when_none_provided` | `create_session()` called when no session sent |
| `test_existing_session_not_recreated` | `create_session()` NOT called when session sent |
| `test_existing_session_id_echoed_in_response` | Response `session_id` matches request |
| `test_rag_query_called_with_correct_query_text` | Correct query text forwarded to `rag_system.query()` |
| `test_missing_query_field_returns_422` | HTTP 422 on missing required field |
| `test_empty_query_string_is_accepted` | Empty `""` query returns 200 |
| `test_sources_reflected_in_response` | Sources from RAG system appear in JSON response |
| `test_rag_exception_returns_500` | HTTP 500 when RAG system raises |
| `test_500_response_includes_detail_message` | Error detail propagated to response body |

#### `GET /api/courses` — 8 tests (`TestCoursesEndpoint`)

| Test | What it validates |
|---|---|
| `test_returns_200` | HTTP 200 |
| `test_response_contains_total_courses` | `total_courses` is an integer |
| `test_response_contains_course_titles_list` | `course_titles` is a list |
| `test_total_courses_matches_titles_length` | Count equals list length |
| `test_course_titles_are_strings` | Every title is a string |
| `test_analytics_method_called` | `get_course_analytics()` called exactly once |
| `test_get_courses_exception_returns_500` | HTTP 500 on analytics failure |
| `test_empty_catalog_returns_zero_courses` | Empty catalog → `total_courses=0, course_titles=[]` |

#### `DELETE /api/session/{session_id}` — 4 tests (`TestDeleteSessionEndpoint`)

| Test | What it validates |
|---|---|
| `test_returns_200_on_valid_session` | HTTP 200 |
| `test_response_contains_success_true` | Body is `{"success": true}` |
| `test_clear_session_called_with_correct_id` | Path parameter forwarded to `clear_session()` |
| `test_clear_session_exception_returns_500` | HTTP 500 on clear failure |

---

## How to run

```bash
# From the repository root
uv run pytest                          # all tests
uv run pytest backend/tests/test_api_endpoints.py   # API tests only
```

All 25 API endpoint tests pass in ~1 second with no external services required.
