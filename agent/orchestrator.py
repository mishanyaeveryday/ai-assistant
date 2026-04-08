from config.settings import GENAI_API_KEY, GENAI_MODEL
from core.llm_client import GeminiClient
from agent.mcp_client import MCPClient
from google.genai import types
from agent.tools_adapter import ToolsAdapter


class AIClient:
    def __init__(self, memory, mcp_client: MCPClient, model=GENAI_MODEL):
        self.llm = GeminiClient(
            llm_model=model,
            api_key=GENAI_API_KEY
        )
        self.mcp_client = mcp_client
        self.tools_adapter = ToolsAdapter(self.mcp_client)
        self.memory = memory  # get_last_5_messages_by_id(chat_id=chat_id)
        self.system_prompt = str(
            """You are AI-Assistant for managing applications and computers.
        You should use tools when it's necessary""")

    async def ask(self, user_prompt: str, temperature: float = 0.3, selected_tool: list = None) -> str:
        contents = self._format_history(memory=self.memory)
        contents.append(types.Content(role='user', parts=[
                        types.Part.from_text(text=user_prompt)]))

        raw_tools = selected_tool or await self.mcp_client.get_tools()
        gemini_tools = [
            self.tools_adapter.mcp_tools_to_gemini_declarations(mcp_tools=raw_tools)]
        print(f'Gemini Tools:{gemini_tools}')
        for _ in range(5):
            response = await self.llm.generate(contents=contents, tools=gemini_tools,
                                               temperature=temperature, system_prompt=self.system_prompt)
            if response.candidates:
                contents.append(response.candidates[0].content)
            if response.function_calls:
                tool_parts = []
                if 'gemini' in self.llm.llm_model:
                    for t in response.function_calls:
                        result = await self.tools_adapter.call_and_format(t.name, t.args)
                        tool_parts.append(result)
                contents.append(types.Content(parts=tool_parts))
                continue
            else:
                break
        return response.text

    def _format_history(self, memory):
        last_messages = []
        for m in memory:
            if 'input' in m:
                last_messages.append(types.Content(
                    role='user', parts=[types.Part.from_text(text=m['input'])]))
            elif 'output' in m and m['output'] != None:
                last_messages.append(types.Content(
                    role='model', parts=[types.Part.from_text(text=m['output'])]))
        return last_messages
