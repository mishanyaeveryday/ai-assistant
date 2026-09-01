import asyncio

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget


class HumanToolApproval:
    """Bridges MCP tool approval to Qt on the GUI thread (safe with qasync).

    Renders the request as an inline approve/deny cell in the chat itself
    (see ApprovalBubble in interface.gui.view) instead of a blocking popup
    window, so long commands stay readable and the chat keeps scrolling.
    """

    def __init__(self, parent_widget: QWidget | None = None):
        self._parent = parent_widget

    async def approve(self, tool_name: str, args: dict) -> bool:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()

        def on_gui_thread() -> None:
            if fut.done():
                return
            try:
                bubble = self._parent.add_approval_request(tool_name, args or {})
            except Exception:
                if not fut.done():
                    fut.set_result(False)
                return

            def on_decided(approved: bool) -> None:
                if not fut.done():
                    fut.set_result(approved)

            bubble.decided.connect(on_decided)

        QTimer.singleShot(0, on_gui_thread)
        return await fut
