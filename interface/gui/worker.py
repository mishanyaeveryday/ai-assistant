from PySide6.QtCore import QObject, Signal
from agent.ai_client import AIClient
from agent.mcp_client import MCPClient
from core.services import AIClientService
import asyncio
# from langchain_mcp_adapters.tools import load_mcp_tools
from async_timeout import timeout


class AIWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, model: AIClientService, chat_id, user_input, mcp_client: MCPClient):
        super().__init__()
        self._model = model
        self.chat_id = chat_id
        self.user_input = user_input
        self.mcp_client = mcp_client

    async def run(self):
        try:

            memory = self._model.load_memory_for_chat(self.chat_id)
            print(f"Memory {memory}")
            print(f'Memory has been initialized')
            langchain_tools = []

            print(f'Status of session: {self.mcp_client.session}')
            # try:
            #     async with timeout(15):
            #         langchain_tools = await load_mcp_tools(self.mcp_client.session)
            # except asyncio.TimeoutError:
            #     self.error.emit("Timeout: MCP server is not responding")
            #     return

            ai_client = AIClient(memory=memory, tools=langchain_tools)

            async with timeout(30):
                message_id = self._model.record_input(
                    self.user_input, chat_id=self.chat_id)
                answer = await ai_client.ask(self.user_input)
            self._model.record_output(
                id=message_id, output=answer, chat_id=self.chat_id)
            self.finished.emit({"output": answer})

        except Exception as e:
            print(f"Error: {str(e)}")
            self.error.emit(str(e))
