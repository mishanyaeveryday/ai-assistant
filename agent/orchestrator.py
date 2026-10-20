import json
from datetime import datetime

from config.settings import (LLM_FALLBACK_MODELS, LLM_MODEL, MAX_TOOL_ROUNDS, OPENROUTER_API_KEY,
                             OPENROUTER_BASE_URL)
from core.llm_client import LLMClient
from agent.tools_adapter import ApproveToolFn, ToolsAdapter, error_result
from agent.tools_policy import ToolsApprovalPolicy


def _response_to_text(message) -> str:
    return (message.content or "").strip()


def date_context(now: datetime) -> str:
    """The model has no other way to know today's date. Left to its training
    data, it treats an earlier year as the present and searches for news,
    prices and versions from back then."""
    return (
        f"Current date and time: {now:%A, %d %B %Y, %H:%M} (UTC{now:%z}). Your training data "
        "is older than that, so for anything that may have changed since - news, prices, "
        "versions, releases, events, anything \"latest\", \"current\" or \"this year\" - use "
        "web_search instead of answering from memory. When a search needs a year, use "
        f"{now.year} unless the user asked about another one.")


class AIClient:
    def __init__(
        self,
        memory,
        mcp_registry,
        tools_approval_policy: ToolsApprovalPolicy | None = None,
        approve_tool: ApproveToolFn | None = None,
        model=LLM_MODEL,
    ):
        self.llm = LLMClient(
            llm_model=model,
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            fallback_models=LLM_FALLBACK_MODELS,
        )
        self.mcp_registry = mcp_registry
        self.tools_adapter = ToolsAdapter(
            mcp_registry,
            tools_approval_policy or ToolsApprovalPolicy(),
            approve_tool=approve_tool,
        )
        self.memory = memory
        # Built per prompt (a client is made for each one), so the date is current.
        self.system_prompt = date_context(datetime.now().astimezone()) + "\n\n" + str(
            """You are an AI assistant that manages files, runs terminal commands, and searches the web on the user's computer using connected tools.

Rules for calling tools:
- Only call a tool when it is actually required to complete the user's request. If you can already answer from context or
 general knowledge, answer directly without calling any tool.
- Never call a tool with empty, placeholder, or guessed arguments. If a required argument (path, content, command, search
 query, etc.) is missing or ambiguous, ask the user for it instead of calling the tool with a blank or made-up value.
- Pick the most specific tool for the job instead of a broader one — e.g. use append_file to add to a file rather than wr
ite_file, which overwrites it; use delete_text to remove part of a file rather than rewriting the whole file.
- Destructive or system-changing tools (deleting or overwriting files, running terminal commands) require the user's expl
icit approval before they run. Only call them when you are confident the arguments are correct, since a bad or unnecessar
y call still interrupts the user with a confirmation prompt.
- If a tool call fails or returns an error, explain what went wrong instead of retrying blindly with the same or empty ar
guments.""")

    async def thinking_loop(
        self,
        count: int = MAX_TOOL_ROUNDS,
        messages: list = None,
        tools: list = None,
        temperature: float = 0.3,
    ):
        if messages is None:
            messages = []
        for _ in range(count):
            message = await self.llm.generate(messages=messages, tools=tools,
                                              temperature=temperature)
            # Sent back whole: reasoning models (Gemini 3 among them) need
            # their reasoning_details to carry on after a tool call.
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                return message
            # Every call needs an answer, or the next request is rejected.
            for call in message.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": await self._run_tool_call(call)})
        # Out of rounds: the last reply was a tool call with no text, which
        # would come out as an empty answer. Make the model answer with what
        # it has found so far instead.
        return await self.llm.generate(messages=messages, tools=tools,
                                       temperature=temperature, tool_choice="none")

    async def _run_tool_call(self, call) -> str:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = None
        if not isinstance(args, dict):
            return error_result("The arguments were not a valid JSON object.")
        print(f"Tool called: {name} args={args}")
        return await self.tools_adapter.call_and_format(name, args)

    async def ask(self, user_prompt: str, temperature: float = 0.3, selected_tool: list = None) -> str:
        self.tools_adapter.generated_images = []
        messages = [{"role": "system", "content": self.system_prompt},
                    *self._format_history(memory=self.memory),
                    {"role": "user", "content": user_prompt}]

        raw_tools = selected_tool or await self.mcp_registry.get_tools()
        # No enabled servers means no tool list at all: some providers reject
        # an empty one.
        tools = self.tools_adapter.mcp_tools_to_openai_tools(
            mcp_tools=raw_tools) if raw_tools else None
        message = await self.thinking_loop(
            messages=messages,
            tools=tools,
            temperature=temperature,
        )
        text = _response_to_text(message)
        if not text:
            # Some models still answer with a tool call after their last round.
            text = (f"(Stopped after {MAX_TOOL_ROUNDS} steps without an answer - "
                    "the task is not finished. Ask me to continue.)")

        for path in self.tools_adapter.generated_images:
            text += f"\n[GENERATED_IMAGE:{path}]"
        return text

    def _format_history(self, memory):
        last_messages = []
        for m in memory:
            if 'input' in m:
                last_messages.append({"role": "user", "content": m['input']})
            elif 'output' in m and m['output'] is not None:
                last_messages.append({"role": "assistant", "content": m['output']})
        return last_messages
