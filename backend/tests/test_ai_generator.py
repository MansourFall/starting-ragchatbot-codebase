"""
Tests for AIGenerator in backend/ai_generator.py.

Verifies that:
  - Direct answers are returned without tool invocation.
  - Conversation history is correctly injected into the system prompt.
  - When Claude requests a tool, tool_manager.execute_tool() is called with
    the right name and arguments.
  - Sequential tool calling works correctly up to MAX_ROUNDS.
  - After MAX_ROUNDS, tools are stripped and Claude is forced to synthesize.

All tests mock the Anthropic client so no real API calls are made.
All tests verify external observable behavior: API call counts, tool names
invoked, and final returned text — not internal message list state.
"""
import pytest
from unittest.mock import MagicMock, patch, call

from ai_generator import AIGenerator
from search_tools import ToolManager


# ---------------------------------------------------------------------------
# Minimal stubs that mimic the Anthropic SDK response objects
# ---------------------------------------------------------------------------

class _Block:
    """Mimics anthropic.types.ContentBlock (text or tool_use)."""

    def __init__(self, type_, *, text=None, name=None, id=None, input=None):
        self.type = type_
        self.text = text
        self.name = name
        self.id = id
        self.input = input or {}


class _Response:
    """Mimics anthropic.types.Message."""

    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def generator():
    return AIGenerator(api_key="test-key", model="claude-test-model")


@pytest.fixture
def tool_manager():
    mgr = MagicMock(spec=ToolManager)
    mgr.execute_tool.return_value = "Mock search result: Python basics covered."
    return mgr


FAKE_TOOLS = [
    {
        "name": "search_course_content",
        "description": "Search course materials.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
]


# ---------------------------------------------------------------------------
# Direct-response tests (no tool use)
# ---------------------------------------------------------------------------

class TestDirectResponse:

    def test_returns_text_on_end_turn(self, generator):
        """stop_reason=end_turn should return the text block directly."""
        resp = _Response(
            content=[_Block("text", text="Python is a programming language.")],
            stop_reason="end_turn",
        )
        with patch.object(generator.client.messages, "create", return_value=resp):
            result = generator.generate_response(query="What is Python?")

        assert result == "Python is a programming language."

    def test_no_previous_conversation_in_prompt_when_history_is_none(self, generator):
        """System prompt must NOT contain 'Previous conversation' when history=None."""
        resp = _Response(content=[_Block("text", text="Answer.")], stop_reason="end_turn")

        with patch.object(generator.client.messages, "create", return_value=resp) as mock_create:
            generator.generate_response(query="test", conversation_history=None)
            system = mock_create.call_args[1]["system"]

        assert "Previous conversation" not in system

    def test_history_injected_into_system_prompt(self, generator):
        """When history is provided it should appear in the system prompt."""
        history = "User: Hello\nAssistant: Hi there"
        resp = _Response(content=[_Block("text", text="Answer.")], stop_reason="end_turn")

        with patch.object(generator.client.messages, "create", return_value=resp) as mock_create:
            generator.generate_response(query="test", conversation_history=history)
            system = mock_create.call_args[1]["system"]

        assert "Previous conversation" in system
        assert history in system

    def test_tools_absent_from_api_params_when_not_provided(self, generator):
        """No 'tools' key should be sent to the API when tools=None."""
        resp = _Response(content=[_Block("text", text="Answer.")], stop_reason="end_turn")

        with patch.object(generator.client.messages, "create", return_value=resp) as mock_create:
            generator.generate_response(query="test", tools=None)
            call_kwargs = mock_create.call_args[1]

        assert "tools" not in call_kwargs

    def test_tool_manager_not_called_on_end_turn(self, generator, tool_manager):
        """tool_manager.execute_tool must NOT be called when stop_reason=end_turn."""
        resp = _Response(
            content=[_Block("text", text="General answer.")],
            stop_reason="end_turn",
        )

        with patch.object(generator.client.messages, "create", return_value=resp):
            generator.generate_response(
                query="What is 2+2?",
                tools=FAKE_TOOLS,
                tool_manager=tool_manager,
            )

        tool_manager.execute_tool.assert_not_called()


# ---------------------------------------------------------------------------
# Tool-use flow tests
# ---------------------------------------------------------------------------

class TestToolUseFlow:

    def test_execute_tool_called_with_correct_name_and_args(self, generator, tool_manager):
        """When Claude requests a tool, execute_tool must be called with the tool name and inputs."""
        tool_block = _Block(
            "tool_use",
            name="search_course_content",
            id="t001",
            input={"query": "Python basics"},
        )
        first_resp = _Response(content=[tool_block], stop_reason="tool_use")
        second_resp = _Response(
            content=[_Block("text", text="Python is great for AI.")],
            stop_reason="end_turn",
        )

        with patch.object(
            generator.client.messages, "create", side_effect=[first_resp, second_resp]
        ):
            result = generator.generate_response(
                query="What is Python?",
                tools=FAKE_TOOLS,
                tool_manager=tool_manager,
            )

        tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="Python basics"
        )
        assert result == "Python is great for AI."

    def test_tool_result_present_in_second_api_call(self, generator, tool_manager):
        """The tool result must appear as a tool_result message in the second API call."""
        tool_block = _Block(
            "tool_use",
            name="search_course_content",
            id="t002",
            input={"query": "deep learning"},
        )
        first_resp = _Response(content=[tool_block], stop_reason="tool_use")
        second_resp = _Response(
            content=[_Block("text", text="Deep learning uses neural networks.")],
            stop_reason="end_turn",
        )

        with patch.object(
            generator.client.messages, "create", side_effect=[first_resp, second_resp]
        ) as mock_create:
            generator.generate_response(
                query="Explain deep learning",
                tools=FAKE_TOOLS,
                tool_manager=tool_manager,
            )

        second_call_messages = mock_create.call_args_list[1][1]["messages"]
        # The last message should be the user-role tool_result
        last_msg = second_call_messages[-1]
        assert last_msg["role"] == "user"
        assert any(
            r.get("type") == "tool_result" and "Mock search result" in r.get("content", "")
            for r in last_msg["content"]
        ), "tool_result with mock content not found in second API call messages"

    def test_tool_use_id_echoed_in_tool_result(self, generator, tool_manager):
        """The tool_use_id in the result must match the id from Claude's tool_use block."""
        tool_block = _Block("tool_use", name="search_course_content", id="unique_id_xyz", input={"query": "q"})
        first_resp = _Response(content=[tool_block], stop_reason="tool_use")
        second_resp = _Response(
            content=[_Block("text", text="Answer.")], stop_reason="end_turn"
        )

        with patch.object(
            generator.client.messages, "create", side_effect=[first_resp, second_resp]
        ) as mock_create:
            generator.generate_response(
                query="test", tools=FAKE_TOOLS, tool_manager=tool_manager
            )

        second_call_messages = mock_create.call_args_list[1][1]["messages"]
        last_msg = second_call_messages[-1]
        tool_result = next(
            r for r in last_msg["content"] if r.get("type") == "tool_result"
        )
        assert tool_result["tool_use_id"] == "unique_id_xyz"


# ---------------------------------------------------------------------------
# Multi-round sequential tool-calling tests
# ---------------------------------------------------------------------------

class TestMultiRoundToolUse:
    """
    Tests for the sequential agentic loop (up to AIGenerator.MAX_ROUNDS rounds).

    All assertions target external observable behavior:
      - Number of API calls made (mock_create.call_count)
      - Which tool names were passed to execute_tool
      - The final string returned by generate_response
    """

    def test_two_tool_rounds_make_exactly_three_api_calls(self, generator, tool_manager):
        """
        Two sequential tool_use responses exhaust MAX_ROUNDS (2).
        The loop strips tools on the third call, which returns end_turn.
        Total: 3 API calls, 2 tool executions.
        """
        block1 = _Block("tool_use", name="search_course_content", id="r1", input={"query": "first"})
        block2 = _Block("tool_use", name="search_course_content", id="r2", input={"query": "second"})

        with patch.object(generator.client.messages, "create", side_effect=[
            _Response(content=[block1], stop_reason="tool_use"),
            _Response(content=[block2], stop_reason="tool_use"),
            _Response(content=[_Block("text", text="Final answer after two searches.")], stop_reason="end_turn"),
        ]) as mock_create:
            result = generator.generate_response(
                query="Multi-step question", tools=FAKE_TOOLS, tool_manager=tool_manager
            )

        assert mock_create.call_count == 3
        assert tool_manager.execute_tool.call_count == 2
        assert result == "Final answer after two searches."

    def test_single_tool_round_early_exit_makes_two_api_calls(self, generator, tool_manager):
        """
        When Claude answers directly after the first tool call (end_turn on
        the second API call), the loop exits early — only 2 total API calls.
        """
        block = _Block("tool_use", name="search_course_content", id="s1", input={"query": "basics"})

        with patch.object(generator.client.messages, "create", side_effect=[
            _Response(content=[block], stop_reason="tool_use"),
            _Response(content=[_Block("text", text="Single-round answer.")], stop_reason="end_turn"),
        ]) as mock_create:
            result = generator.generate_response(
                query="What is ML?", tools=FAKE_TOOLS, tool_manager=tool_manager
            )

        assert mock_create.call_count == 2
        assert tool_manager.execute_tool.call_count == 1
        assert result == "Single-round answer."

    def test_tools_absent_from_api_call_after_max_rounds_reached(self, generator, tool_manager):
        """
        After MAX_ROUNDS tool invocations, the next API call must not include
        a 'tools' parameter — this forces Claude to produce a text answer.
        The first two calls must still include tools.
        """
        block = _Block("tool_use", name="search_course_content", id="x1", input={"query": "q"})

        with patch.object(generator.client.messages, "create", side_effect=[
            _Response(content=[block], stop_reason="tool_use"),   # round 0 — tools included
            _Response(content=[block], stop_reason="tool_use"),   # round 1 — tools included
            _Response(content=[_Block("text", text="Forced final.")], stop_reason="end_turn"),
        ]) as mock_create:
            result = generator.generate_response(
                query="q", tools=FAKE_TOOLS, tool_manager=tool_manager
            )

        calls = mock_create.call_args_list
        assert "tools" in calls[0][1], "First call must include tools"
        assert "tools" in calls[1][1], "Second call (round 1) must include tools"
        assert "tools" not in calls[2][1], "Third call must NOT include tools (ceiling enforced)"
        assert result == "Forced final."

    def test_both_tool_names_executed_in_correct_order_across_two_rounds(self, generator, tool_manager):
        """
        Different tools called in round 0 and round 1 must each be forwarded
        to execute_tool with the correct name and arguments, in order.
        """
        tool_manager.execute_tool.side_effect = ["Catalog result.", "Outline result."]

        block1 = _Block("tool_use", name="search_course_content", id="a1", input={"query": "find course"})
        block2 = _Block("tool_use", name="get_course_outline",    id="a2", input={"course_name": "Course X"})

        with patch.object(generator.client.messages, "create", side_effect=[
            _Response(content=[block1], stop_reason="tool_use"),
            _Response(content=[block2], stop_reason="tool_use"),
            _Response(content=[_Block("text", text="Here is the outline.")], stop_reason="end_turn"),
        ]):
            result = generator.generate_response(
                query="Get outline for Course X", tools=FAKE_TOOLS, tool_manager=tool_manager
            )

        assert tool_manager.execute_tool.call_count == 2
        first_name  = tool_manager.execute_tool.call_args_list[0][0][0]
        second_name = tool_manager.execute_tool.call_args_list[1][0][0]
        assert first_name  == "search_course_content"
        assert second_name == "get_course_outline"
        assert result == "Here is the outline."

    def test_tool_execution_error_handled_gracefully(self, generator, tool_manager):
        """
        When execute_tool raises an exception, the error is caught, a descriptive
        string is forwarded to Claude as the tool_result, and generate_response
        still returns a valid string — no exception propagates to the caller.
        """
        tool_manager.execute_tool.side_effect = RuntimeError("ChromaDB unavailable")

        block = _Block("tool_use", name="search_course_content", id="e1", input={"query": "q"})

        with patch.object(generator.client.messages, "create", side_effect=[
            _Response(content=[block], stop_reason="tool_use"),
            _Response(content=[_Block("text", text="I could not retrieve results.")], stop_reason="end_turn"),
        ]):
            result = generator.generate_response(
                query="q", tools=FAKE_TOOLS, tool_manager=tool_manager
            )

        assert isinstance(result, str)
        assert result == "I could not retrieve results."
