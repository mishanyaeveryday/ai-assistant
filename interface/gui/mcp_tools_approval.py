import asyncio
import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QWidget


class HumanToolApproval:
    """Bridges MCP tool approval to Qt on the GUI thread (safe with qasync)."""

    def __init__(self, parent_widget: QWidget | None = None):
        self._parent = parent_widget

    async def approve(self, tool_name: str, args: dict) -> bool:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        payload = self._format_payload(tool_name, args)

        def on_gui_thread() -> None:
            try:
                if fut.done():
                    return
                result = QMessageBox.question(
                    self._parent,
                    "Approve terminal / sensitive tool",
                    payload,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                approved = result == QMessageBox.StandardButton.Yes
            except Exception:
                if not fut.done():
                    fut.set_result(False)
                return
            if not fut.done():
                fut.set_result(approved)

        QTimer.singleShot(0, on_gui_thread)
        return await fut

    @staticmethod
    def _format_payload(tool_name: str, args: dict) -> str:
        try:
            body = json.dumps(args, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            body = str(args)
        return (
            "The assistant wants to run this tool on your machine.\n\n"
            f"Tool: {tool_name}\n\nArguments:\n{body}\n\nAllow execution?"
        )
