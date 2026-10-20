import asyncio
from dataclasses import dataclass, field

import shiboken6

from agent.tools_adapter import ApproveToolFn


@dataclass
class ApprovalRequest:
    chat_id: str
    tool_name: str
    args: dict
    future: asyncio.Future
    # None while waiting, then "approved", "denied" or "stopped".
    outcome: str | None = None
    # The card showing it, if its chat is open; rebuilt when it is reopened.
    bubble: object = field(default=None, repr=False)


class HumanToolApproval:
    """Bridges MCP tool approval to the chat (safe with qasync).

    Renders the request as an inline approve/deny cell in the chat itself
    (see ApprovalBubble in interface.gui.view) instead of a blocking popup
    window, so long commands stay readable and the chat keeps scrolling.

    The requests are kept here, not in the cards: a chat's widgets are torn
    down whenever another chat is opened, and a request still waiting for an
    answer has to survive that and be shown again when its chat comes back.
    """

    def __init__(self, view):
        self._view = view
        self._requests: list[ApprovalRequest] = []

    def for_chat(self, chat_id: str) -> ApproveToolFn:
        async def approve(tool_name: str, args: dict) -> bool:
            return await self._ask(chat_id, tool_name, args or {})
        return approve

    async def _ask(self, chat_id: str, tool_name: str, args: dict) -> bool:
        request = ApprovalRequest(chat_id, tool_name, args,
                                  asyncio.get_running_loop().create_future())
        self._requests.append(request)
        self._show(request)
        try:
            return await request.future
        except asyncio.CancelledError:
            # The task was stopped while waiting; its buttons would otherwise
            # stay clickable for a call that is never going to happen.
            request.outcome = "stopped"
            if request.bubble is not None and shiboken6.isValid(request.bubble):
                request.bubble.mark_stopped()
            raise

    def _show(self, request: ApprovalRequest):
        if self._view.current_chat_id != request.chat_id:
            return
        request.bubble = self._view.add_approval_request(
            request.tool_name, request.args, request.outcome)
        if request.outcome is None:
            request.bubble.decided.connect(
                lambda approved, r=request: self._decide(r, approved))

    @staticmethod
    def _decide(request: ApprovalRequest, approved: bool):
        if request.future.done():
            return
        request.outcome = "approved" if approved else "denied"
        request.future.set_result(approved)

    def show_chat(self, chat_id: str):
        """Puts the current task's cards back into its chat, which was just
        rebuilt from history - the ones still waiting with their buttons."""
        for request in self._requests:
            if request.chat_id == chat_id:
                self._show(request)

    def clear(self):
        """The task is over; its cards are not needed again."""
        self._requests.clear()