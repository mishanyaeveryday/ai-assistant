import asyncio
import os
import sqlite3
import sys
import time
from unittest.mock import patch

import pytest

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from agent.orchestrator import WORKSPACE_LISTING_LIMIT, workspace_context  # noqa: E402
from core.services import ChatService  # noqa: E402
from db.database import Chat_DB  # noqa: E402
from interface.gui.worker import AIWorker  # noqa: E402
from mcp_tools.code_interpreter.server import _new_images  # noqa: E402

USER_ID = "user-1"


@pytest.fixture
def default_dir(tmp_path):
    folder = tmp_path / "default workspace"
    with patch("core.services.WORKSPACE_DIR", str(folder)):
        yield folder


@pytest.fixture
def chats(tmp_path, default_dir):
    db = Chat_DB(db_name=str(tmp_path / "test.sqlite3"))
    db.create_table()
    service = ChatService(chat_db=db)
    service.create_new_chat(user_id=USER_ID, chat_title="A")
    return service


def chat_id(chats):
    return chats.get_all_user_chats(USER_ID)[0].id


# --- Storing the folder ---

def test_create_table_adds_the_column_to_an_existing_database(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE chats (id TEXT PRIMARY KEY, title TEXT, "
                     "user_id TEXT, created_at TEXT)")
        conn.execute("INSERT INTO chats VALUES ('c1', 'Old', 'u', 'now')")

    Chat_DB(db_name=path).create_table()

    service = ChatService(chat_db=Chat_DB(db_name=path))
    assert service.get_chat("c1").workspace is None


def test_a_new_chat_works_in_the_default_folder(chats, default_dir):
    cid = chat_id(chats)

    assert chats.get_workspace(cid) == str(default_dir.resolve())
    assert chats.is_default_workspace(cid)
    # Made on first use, as the servers used to on start-up.
    assert default_dir.is_dir()


def test_a_picked_folder_is_kept(chats, tmp_path):
    cid = chat_id(chats)
    folder = tmp_path / "Документы" / "my folder"
    folder.mkdir(parents=True)

    chats.set_workspace(cid, str(folder))

    assert chats.get_workspace(cid) == str(folder.resolve())
    assert not chats.is_default_workspace(cid)


def test_picking_the_default_folder_stores_no_folder(chats, default_dir):
    cid = chat_id(chats)
    default_dir.mkdir()

    chats.set_workspace(cid, str(default_dir))

    assert chats.get_chat(cid).workspace is None


def test_reset_goes_back_to_the_default(chats, tmp_path, default_dir):
    cid = chat_id(chats)
    chats.set_workspace(cid, str(tmp_path))

    chats.set_workspace(cid, None)

    assert chats.get_workspace(cid) == str(default_dir.resolve())


def test_a_missing_folder_is_refused(chats, tmp_path):
    cid = chat_id(chats)

    with pytest.raises(ValueError):
        chats.set_workspace(cid, str(tmp_path / "gone"))

    assert chats.is_default_workspace(cid)


def test_a_missing_picked_folder_is_not_recreated(chats, tmp_path):
    cid = chat_id(chats)
    folder = tmp_path / "picked"
    folder.mkdir()
    chats.set_workspace(cid, str(folder))
    folder.rmdir()

    # The servers report it missing instead of writing into a new empty one.
    assert chats.get_workspace(cid) == str(folder.resolve())
    assert not folder.exists()


# --- What the model is told ---

def test_context_names_the_folder_and_its_top_level(tmp_path):
    (tmp_path / "report.md").write_text("x")
    (tmp_path / "data").mkdir()
    (tmp_path / ".git").mkdir()

    text = workspace_context(str(tmp_path))

    assert str(tmp_path) in text
    assert "data/, report.md" in text
    assert ".git" not in text


def test_context_caps_the_listing(tmp_path):
    for i in range(WORKSPACE_LISTING_LIMIT + 5):
        (tmp_path / f"f{i:03}.txt").write_text("")

    text = workspace_context(str(tmp_path))

    assert "(and 5 more)" in text
    assert f"f{WORKSPACE_LISTING_LIMIT:03}.txt" not in text


def test_context_of_a_missing_folder_says_so(tmp_path):
    assert "cannot be read" in workspace_context(str(tmp_path / "gone"))


# --- A task works in its chat's folder ---

def test_worker_points_the_servers_at_the_chat_folder_before_asking(tmp_path):
    events = []

    class Model:
        def load_memory_for_chat(self, chat_id):
            return []

        def record_input(self, text, chat_id):
            # Recorded before anything is awaited, so a Stop can't lose it.
            events.append(("record", text))
            return "message-1"

        def record_output(self, id, output, chat_id):
            pass

    class Registry:
        async def set_workspace(self, path):
            events.append(("roots", path))

    class Client:
        def __init__(self, workspace=None, **kwargs):
            events.append(("prompt", workspace))

        async def ask(self, prompt):
            events.append(("ask", None))
            return "done"

    worker = AIWorker(Model(), "A", "hi", mcp_registry=Registry(),
                      approve_tool=None, workspace=str(tmp_path))
    with patch("interface.gui.worker.AIClient", Client):
        asyncio.run(worker.run())

    assert events == [("prompt", str(tmp_path)), ("record", "hi"),
                      ("roots", str(tmp_path)), ("ask", None)]


def test_controller_gives_the_task_its_chat_folder(chats, tmp_path):
    from PySide6.QtCore import QObject, Signal

    from interface.gui import controller as controller_module
    from interface.gui.controller import AIClientController

    class View(QObject):
        send_input = Signal(str, str)
        stop_requested = Signal()
        chat_shown = Signal(str)
        chat_delete_requested = Signal(str)
        logout_requested = Signal()
        current_chat_id = None

        def set_busy_chat(self, chat_id):
            pass

    class Worker(QObject):
        finished = Signal(dict)
        error = Signal(str)
        stopped = Signal()
        workspaces = []

        def __init__(self, *args, workspace=None, **kwargs):
            super().__init__()
            Worker.workspaces.append(workspace)

        async def run(self):
            pass

    cid = chat_id(chats)
    chats.set_workspace(cid, str(tmp_path))
    controller = AIClientController(model=None, view=View(), mcp_registry=None,
                                    chat_model=chats)

    async def scenario():
        controller.handle_prompt(cid, "hi")
        await controller._task

    with patch.object(controller_module, "AIWorker", Worker):
        asyncio.run(scenario())

    assert Worker.workspaces == [str(tmp_path.resolve())]


# --- Charts saved by the Python sandbox ---

def test_new_images_skips_old_hidden_vendor_and_deep_files(tmp_path):
    since = time.time() - 1
    old = tmp_path / "old.png"
    old.write_bytes(b"")
    os.utime(old, (since - 100, since - 100))
    (tmp_path / "chart.png").write_bytes(b"")
    (tmp_path / "out" / "plots").mkdir(parents=True)
    (tmp_path / "out" / "plots" / "nested.png").write_bytes(b"")
    for skipped in (".cache", "node_modules", "a/b/c/d"):
        (tmp_path / skipped).mkdir(parents=True, exist_ok=True)
        (tmp_path / skipped / "x.png").write_bytes(b"")

    found = {p.relative_to(tmp_path).as_posix() for p in _new_images(tmp_path, since)}

    assert found == {"chart.png", "out/plots/nested.png"}
