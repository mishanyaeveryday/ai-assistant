from PySide6.QtCore import QObject, Signal
from agent.orchestrator import AIClient
from agent.mcp_client import MCPClient
from agent.tools_adapter import ApproveToolFn
from agent.tools_policy import ToolsApprovalPolicy
from core.services import AIClientService


class AIWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        model: AIClientService,
        chat_id,
        user_input,
        mcp_client: MCPClient,
        approve_tool: ApproveToolFn | None,
        tools_approval_policy: ToolsApprovalPolicy | None = None,
    ):
        super().__init__()
        self._model = model
        self.chat_id = chat_id
        self.user_input = user_input
        self.mcp_client = mcp_client
        self.approve_tool = approve_tool
        self.tools_approval_policy = tools_approval_policy

    async def run(self):
        try:
            memory = self._model.load_memory_for_chat(self.chat_id)
            print(f"Memory {memory}")

            ai_client = AIClient(
                mcp_client=self.mcp_client,
                memory=memory,
                approve_tool=self.approve_tool,
                tools_approval_policy=self.tools_approval_policy or ToolsApprovalPolicy(),
            )

            message_id = self._model.record_input(
                self.user_input, chat_id=self.chat_id)
            answer = await ai_client.ask(self.user_input)
            self._model.record_output(
                id=message_id, output=answer, chat_id=self.chat_id)
            self.finished.emit({"output": answer})

        except Exception as e:
            print(f"Error: {str(e)}")
            self.error.emit(str(e))
