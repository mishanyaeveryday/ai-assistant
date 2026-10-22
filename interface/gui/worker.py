import asyncio

from PySide6.QtCore import QObject, Signal
from agent.orchestrator import AIClient
from agent.tools_adapter import ApproveToolFn
from agent.tools_policy import ToolsApprovalPolicy
from core.services import AIClientService

# Saved as the answer of a task the user stopped, so the history never holds
# a question without one - and the model can see on the next prompt that its
# previous task was cut short.
STOPPED_OUTPUT = "(Stopped by the user.)"


class AIWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)
    stopped = Signal()

    def __init__(
        self,
        model: AIClientService,
        chat_id,
        user_input,
        mcp_registry,
        approve_tool: ApproveToolFn | None,
        tools_approval_policy: ToolsApprovalPolicy | None = None,
        workspace: str | None = None,
    ):
        super().__init__()
        self._model = model
        self.chat_id = chat_id
        self.user_input = user_input
        self.mcp_registry = mcp_registry
        self.approve_tool = approve_tool
        self.tools_approval_policy = tools_approval_policy
        # Taken when the task starts: picking another folder for the chat
        # mid-task must not move the files it is working on.
        self.workspace = workspace

    async def run(self):
        message_id = None
        try:
            memory = self._model.load_memory_for_chat(self.chat_id)
            print(f"Memory {memory}")

            ai_client = AIClient(
                mcp_registry=self.mcp_registry,
                memory=memory,
                approve_tool=self.approve_tool,
                tools_approval_policy=self.tools_approval_policy or ToolsApprovalPolicy(),
                workspace=self.workspace,
            )

            message_id = self._model.record_input(
                self.user_input, chat_id=self.chat_id)
            # Before the first tool call, so every server works in this
            # chat's folder rather than the previous task's. After the prompt
            # is recorded: telling running servers can be awaited, and a Stop
            # landing there must still leave the prompt in the history.
            await self.mcp_registry.set_workspace(self.workspace)
            answer = await ai_client.ask(self.user_input)
            self._model.record_output(
                id=message_id, output=answer, chat_id=self.chat_id)
            self.finished.emit({"output": answer})

        except asyncio.CancelledError:
            if message_id is not None:
                self._model.record_output(
                    id=message_id, output=STOPPED_OUTPUT, chat_id=self.chat_id)
            self.stopped.emit()
            raise

        except Exception as e:
            print(f"Error: {str(e)}")
            self.error.emit(str(e))
