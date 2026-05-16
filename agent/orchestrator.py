from config.settings import GENAI_API_KEY, GENAI_MODEL
from core.llm_client import GeminiClient
from agent.mcp_client import MCPClient
from google.genai import types
from agent.tools_adapter import ApproveToolFn, ToolsAdapter
from agent.tools_policy import ToolsApprovalPolicy


def _response_to_text(response) -> str:
    text = getattr(response, "text", None)
    if text is not None and str(text).strip():
        return str(text).strip()
    cand = response.candidates[0] if response.candidates else None
    if not cand or not cand.content:
        return ""
    parts_out = []
    for p in cand.content.parts or []:
        if getattr(p, "text", None):
            parts_out.append(p.text)
        elif getattr(p, "thought", None):
            continue
    return "\n".join(parts_out).strip()


class AIClient:
    def __init__(
        self,
        memory,
        mcp_client: MCPClient,
        tools_approval_policy: ToolsApprovalPolicy | None = None,
        approve_tool: ApproveToolFn | None = None,
        model=GENAI_MODEL,
    ):
        self.llm = GeminiClient(
            llm_model=model,
            api_key=GENAI_API_KEY
        )
        self.mcp_client = mcp_client
        self.tools_adapter = ToolsAdapter(
            mcp_client,
            tools_approval_policy or ToolsApprovalPolicy(),
            approve_tool=approve_tool,
        )
        self.memory = memory
        self.system_prompt = str(
            """You are AI-Assistant for managing applications and computers.
        You should use tools when it's necessary.""")

    async def thinking_loop(
        self,
        count: int = 5,
        contents: list = None,
        gemini_tools: types.Tool = None,
        temperature: float = 0.3,
    ):
        if contents is None:
            contents = []
        response = None
        for _ in range(count):
            response = await self.llm.generate(contents=contents, tools=gemini_tools,
                                               temperature=temperature, system_prompt=self.system_prompt)
            if response.candidates:
                contents.append(response.candidates[0].content)
            if getattr(response, "function_calls", None):
                tool_parts = []
                if 'gemini' in self.llm.llm_model:
                    for t in response.function_calls:
                        raw_args = getattr(t, "args", None)
                        args = raw_args if isinstance(raw_args, dict) else {}
                        part = await self.tools_adapter.call_and_format(t.name, args)
                        if part is not None:
                            tool_parts.append(part)
                contents.append(types.Content(parts=tool_parts))
                continue
            break
        return response

    async def ask(self, user_prompt: str, temperature: float = 0.3, selected_tool: list = None) -> str:
        contents = self._format_history(memory=self.memory)
        contents.append(types.Content(role='user', parts=[
                        types.Part.from_text(text=user_prompt)]))

        raw_tools = selected_tool or await self.mcp_client.get_tools()
        gemini_tools = [
            self.tools_adapter.mcp_tools_to_gemini_declarations(mcp_tools=raw_tools)]
        print(f'Gemini Tools:{gemini_tools}')
        response = await self.thinking_loop(
            count=5,
            contents=contents,
            gemini_tools=gemini_tools,
            temperature=temperature,
        )
        if response is None or not getattr(response, "candidates", None):
            return "Sorry — no reply from the model."
        return _response_to_text(response)

    def _format_history(self, memory):
        last_messages = []
        for m in memory:
            if 'input' in m:
                last_messages.append(types.Content(
                    role='user', parts=[types.Part.from_text(text=m['input'])]))
            elif 'output' in m and m['output'] is not None:
                last_messages.append(types.Content(
                    role='model', parts=[types.Part.from_text(text=m['output'])]))
        return last_messages
