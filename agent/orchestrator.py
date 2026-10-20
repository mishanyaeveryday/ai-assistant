import json

from config.settings import LLM_FALLBACK_MODELS, LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from core.llm_client import LLMClient
from agent.tools_adapter import ApproveToolFn, ToolsAdapter, error_result
from agent.tools_policy import ToolsApprovalPolicy


def _response_to_text(message) -> str:
    return (message.content or "").strip()


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
        self.system_prompt = str(
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
        count: int = 5,
        messages: list = None,
        tools: list = None,
        temperature: float = 0.3,
    ):
        if messages is None:
            messages = []
        message = None
        for _ in range(count):
            message = await self.llm.generate(messages=messages, tools=tools,
                                              temperature=temperature)
            # Sent back whole: reasoning models (Gemini 3 among them) need
            # their reasoning_details to carry on after a tool call.
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                break
            # Every call needs an answer, or the next request is rejected.
            for call in message.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": await self._run_tool_call(call)})
        return message

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
            count=5,
            messages=messages,
            tools=tools,
            temperature=temperature,
        )
        if message is None:
            text = "Sorry — no reply from the model."
        else:
            text = _response_to_text(message)

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
