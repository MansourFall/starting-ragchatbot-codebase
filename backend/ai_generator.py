import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    # Maximum number of sequential tool-calling rounds per user query.
    # After MAX_ROUNDS the tools parameter is withheld, forcing Claude to synthesize.
    MAX_ROUNDS = 2

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use the search tool **only** for questions about specific course content or detailed educational materials
- You may perform **up to two sequential searches** if the first result is insufficient or a follow-up lookup is genuinely needed to fully answer the question. Use this sparingly.
- After all searches are complete, synthesize results into a single, accurate, fact-based response
- If searches yield no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **Course outline / syllabus questions**: Use the `get_course_outline` tool. Return the course title, course link, and the complete lesson list with every lesson number and lesson title.
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional sequential tool usage and conversation context.

        Supports up to MAX_ROUNDS sequential tool-calling rounds. Each round is a
        separate API call, allowing Claude to reason about previous results before
        deciding whether to call another tool or synthesize a final answer.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """
        # Build system content — inject conversation history when present
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Seed the messages list; it grows in-place across tool-calling rounds
        messages = [{"role": "user", "content": query}]

        rounds = 0

        while True:
            # Strip tools once the ceiling is reached so Claude is forced to synthesize
            tools_for_this_call = tools if rounds < self.MAX_ROUNDS else None

            api_params: Dict[str, Any] = {
                **self.base_params,
                "system": system_content,
                "messages": messages,
            }
            if tools_for_this_call:
                api_params["tools"] = tools_for_this_call
                api_params["tool_choice"] = {"type": "auto"}

            response = self.client.messages.create(**api_params)

            # Exit when Claude produces a text answer (or no tool_manager is available)
            if response.stop_reason != "tool_use" or not tool_manager:
                return response.content[0].text

            # ---- Inline tool execution ----
            # Append Claude's assistant turn (may contain tool_use blocks + optional text)
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        result_content = tool_manager.execute_tool(block.name, **block.input)
                    except Exception as exc:
                        # Pass the error back to Claude so it can acknowledge and recover
                        result_content = f"Tool execution failed: {exc}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    })

            # Append all tool results as a single user turn
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            rounds += 1
            # Loop back — next iteration Claude sees the results and decides what to do
