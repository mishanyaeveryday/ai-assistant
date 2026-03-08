from tools.code_interpreter import CodeGenerator, DockerCodeInterpreter
from config.settings import GENAI_API_KEY, GENAI_MODEL
from core.llm_client import GeminiClient
from agent.mcp_client import MCPClient
from google.genai import types
from db.database import MessageHistory_DB


class AIClient:
    def __init__(self, memory, tools, model=GENAI_MODEL):
        self.llm = GeminiClient(
            llm_model=model,
            api_key=GENAI_API_KEY
        )
        self.mcp_client = MCPClient()
        self.memory = memory  # get_last_5_messages_by_id(chat_id=chat_id)
        self.tools = tools
        self.system_prompt = str(
            """You are AI-Assistant for managing applications and computers.
        You should use tools when it's necessary""")

    async def ask(self, user_prompt: str, temperature: float = 0.3, selected_tool: list = None) -> str:

        contents = self._format_history(memory=self.memory)
        contents.append(types.Content(role='user', parts=[
                        types.Part.from_text(text=user_prompt)]))

        tools = selected_tool or self.tools
        for _ in range(5):
            response = await self.llm.generate(contents=contents, tools=tools,
                                               temperature=temperature, system_prompt=self.system_prompt)
            if response.function_calls:
                for t in response.function_calls:
                    result = await self.mcp_client.call_tool(t['name'], t['args'])
                    contents.append(types.Part.from_function_response(result))
            else:
                break
        return response.text

    def _format_history(self, memory):
        last_messages = []
        for m in memory:
            last_messages.append(types.Content(role='user', parts=m['input']))
            if m['output'] != None:
                last_messages.append(types.Content(
                    role='model', parts=m['output']))
        return last_messages
