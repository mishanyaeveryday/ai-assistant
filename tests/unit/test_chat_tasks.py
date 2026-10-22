import asyncio
import os
import sys
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from interface.gui import controller as controller_module  # noqa: E402
from interface.gui.controller import AIClientController, ViewManager  # noqa: E402
from interface.gui.worker import STOPPED_OUTPUT, AIWorker  # noqa: E402


class FakeBubble(QObject):
    decided = Signal(bool)

    def __init__(self, outcome):
        super().__init__()
        self.outcome = outcome

    def mark_stopped(self):
        if self.outcome is None:
            self.outcome = "stopped"

    def click(self, approved):
        self.outcome = "approved" if approved else "denied"
        self.decided.emit(approved)


class FakeView(QObject):
    """The parts of ChatPage the controller uses. Opening a chat throws its
    cards away and emits chat_shown, as the real page does."""

    send_input = Signal(str, str)
    stop_requested = Signal()
    chat_shown = Signal(str)
    chat_delete_requested = Signal(str)
    logout_requested = Signal()

    def __init__(self):
        super().__init__()
        self.current_chat_id = None
        self.busy_chat_id = None
        self.replies = []
        self.cards = []

    def open_chat(self, chat_id):
        self.current_chat_id = chat_id
        self.cards = []
        self.chat_shown.emit(chat_id)

    def set_busy_chat(self, chat_id):
        self.busy_chat_id = chat_id

    def add_assistant_message(self, text):
        self.replies.append((self.current_chat_id, text))

    def add_approval_request(self, tool_name, args, outcome=None):
        bubble = FakeBubble(outcome)
        self.cards.append((tool_name, bubble))
        return bubble


class FakeWorker(QObject):
    """Asks to approve `write_file`, then answers with whether it was allowed."""

    finished = Signal(dict)
    error = Signal(str)
    stopped = Signal()
    started = []

    def __init__(self, model, chat_id, user_input, mcp_registry, approve_tool,
                 tools_approval_policy=None, workspace=None):
        super().__init__()
        self.chat_id = chat_id
        self.approve_tool = approve_tool
        FakeWorker.started.append(chat_id)

    async def run(self):
        try:
            allowed = await self.approve_tool("write_file", {"path": "notes.md"})
            self.finished.emit({"output": f"allowed={allowed}"})
        except asyncio.CancelledError:
            self.stopped.emit()
            raise


def make_controller():
    FakeWorker.started = []
    view = FakeView()
    controller = AIClientController(model=None, view=view, mcp_registry=None)
    return controller, view


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


def run(scenario):
    with patch.object(controller_module, "AIWorker", FakeWorker):
        asyncio.run(scenario())


def test_waiting_approval_survives_opening_another_chat():
    async def scenario():
        controller, view = make_controller()
        view.open_chat("A")
        view.send_input.emit("A", "save my notes")
        await settle()
        assert [name for name, _ in view.cards] == ["write_file"]

        view.open_chat("B")
        await settle()
        assert view.cards == []                      # not shown in the wrong chat
        assert view.busy_chat_id == "A"              # and the task is still on

        view.open_chat("A")
        tool_name, card = view.cards[0]
        assert (tool_name, card.outcome) == ("write_file", None)   # still asking

        card.click(True)
        await settle()
        assert view.replies == [("A", "allowed=True")]
        assert view.busy_chat_id is None

    run(scenario)


def test_answered_card_comes_back_answered():
    async def scenario():
        controller, view = make_controller()

        async def ask_twice(self):
            await self.approve_tool("terminal_command", {"command": "ls"})
            await self.approve_tool("write_file", {"path": "notes.md"})
        with patch.object(FakeWorker, "run", ask_twice):
            view.open_chat("A")
            view.send_input.emit("A", "list and save")
            await settle()
            view.cards[0][1].click(False)
            await settle()

            view.open_chat("B")
            view.open_chat("A")
            assert [(name, card.outcome) for name, card in view.cards] == [
                ("terminal_command", "denied"), ("write_file", None)]
            controller.stop()
            await settle()

    run(scenario)


def test_only_one_task_runs_at_a_time():
    async def scenario():
        controller, view = make_controller()
        view.open_chat("A")
        view.send_input.emit("A", "first")
        view.open_chat("B")
        view.send_input.emit("B", "second")
        await settle()

        assert FakeWorker.started == ["A"]
        controller.stop()
        await settle()

    run(scenario)


def test_answer_goes_to_its_own_chat_only():
    async def scenario():
        controller, view = make_controller()
        view.open_chat("A")
        view.send_input.emit("A", "save my notes")
        await settle()
        _, card = view.cards[0]

        view.open_chat("B")
        card.click(True)       # a card kept from before, answered late
        await settle()

        assert view.replies == []
        assert view.busy_chat_id is None

    run(scenario)


def test_stop_ends_the_task_and_marks_the_waiting_card():
    async def scenario():
        controller, view = make_controller()
        view.open_chat("A")
        view.send_input.emit("A", "save my notes")
        await settle()
        _, card = view.cards[0]

        view.stop_requested.emit()
        await settle()

        assert card.outcome == "stopped"
        assert view.replies == [("A", STOPPED_OUTPUT)]
        assert view.busy_chat_id is None
        assert not controller.is_running

    run(scenario)


def test_deleting_the_running_chat_stops_its_task():
    async def scenario():
        controller, view = make_controller()
        view.open_chat("A")
        view.send_input.emit("A", "save my notes")
        await settle()

        view.chat_delete_requested.emit("B")
        await settle()
        assert controller.is_running

        view.chat_delete_requested.emit("A")
        await settle()
        assert not controller.is_running

    run(scenario)


def test_stopped_worker_records_the_stop():
    class Model:
        def __init__(self):
            self.outputs = []

        def load_memory_for_chat(self, chat_id):
            return []

        def record_input(self, text, chat_id):
            return "message-1"

        def record_output(self, id, output, chat_id):
            self.outputs.append((id, output))

    class SlowClient:
        def __init__(self, **kwargs):
            pass

        async def ask(self, prompt):
            await asyncio.Event().wait()

    class Registry:
        async def set_workspace(self, path):
            pass

    model = Model()
    worker = AIWorker(model, "A", "hi", mcp_registry=Registry(), approve_tool=None)
    stopped = []
    worker.stopped.connect(lambda: stopped.append(True))

    async def scenario():
        task = asyncio.create_task(worker.run())
        await settle()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    with patch("interface.gui.worker.AIClient", SlowClient):
        asyncio.run(scenario())

    assert model.outputs == [("message-1", STOPPED_OUTPUT)]
    assert stopped == [True]


# --- Logging out ---

class FakePage:
    def __init__(self):
        self.current_chat_id = None

    def clear_chat_view(self):
        self.current_chat_id = None


class FakeWindow:
    def __init__(self):
        self.shown = None

    def show_page(self, page):
        self.shown = page


def test_logout_closes_the_open_chat():
    # Built without __init__, which connects the pages' signals to this plain
    # object: freeing such a receiver before its senders corrupts memory in
    # PySide 6.9, and a test's manager is always freed first. The app makes
    # one that lives as long as the pages.
    manager = ViewManager.__new__(ViewManager)
    manager.app_window, manager.main_view, manager.login_view = (
        FakeWindow(), FakePage(), FakePage())
    manager.main_view.current_chat_id = "previous-users-chat"

    manager.handle_logout()

    assert manager.main_view.current_chat_id is None
    assert manager.app_window.shown is manager.login_view
