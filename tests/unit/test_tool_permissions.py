"""Letting chosen tools run without asking, per user, from settings."""
import asyncio
import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from agent.mcp_registry import MCPRegistry  # noqa: E402
from agent.tools_adapter import ToolsAdapter  # noqa: E402
from agent.tools_policy import ToolsApprovalPolicy  # noqa: E402
from core.services import MCPServerService  # noqa: E402
from db.database import MCPServer_DB  # noqa: E402
from interface.gui.controller import MCPServersController  # noqa: E402
from tests.unit.test_mcp_servers_settings import FakeView  # noqa: E402

USER_ID = "user-1"


@pytest.fixture
def service(tmp_path):
    db = MCPServer_DB(db_name=str(tmp_path / "test.sqlite3"))
    db.create_table()
    return MCPServerService(mcp_server_db=db)


def add_server(service, name, tools, user_id=USER_ID, builtin=False):
    server_id = service.mcp_server_db.add_server(
        user_id=user_id, name=name, transport='stdio', command='npx',
        is_builtin=builtin)
    service.update_server(server_id, known_tools=[
        {'name': tool, 'description': f'{tool} does things', 'inputSchema': {}}
        for tool in tools])
    return server_id


# --- Storing it ---

def test_create_table_adds_the_column_to_an_existing_database(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE mcp_servers (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            transport TEXT NOT NULL, command TEXT, args TEXT, env TEXT, url TEXT,
            headers TEXT, description TEXT, is_builtin INTEGER DEFAULT 0,
            is_enabled INTEGER DEFAULT 1, created_at TEXT)""")
        conn.execute("INSERT INTO mcp_servers (id, user_id, name, transport) "
                     "VALUES ('s1', 'u', 'old', 'stdio')")

    MCPServer_DB(db_name=path).create_table()

    service = MCPServerService(mcp_server_db=MCPServer_DB(db_name=path))
    assert service.get_server('s1').auto_approved_tools == []
    service.set_tool_auto_approved('s1', 'search', True)
    assert service.get_server('s1').auto_approved_tools == ['search']


def test_allowing_and_taking_back(service):
    server_id = add_server(service, 'github', ['search', 'create_issue'])

    service.set_tool_auto_approved(server_id, 'search', True)
    service.set_tool_auto_approved(server_id, 'create_issue', True)
    service.set_tool_auto_approved(server_id, 'search', True)
    assert service.get_server(server_id).auto_approved_tools == ['create_issue', 'search']

    service.set_tool_auto_approved(server_id, 'search', False)
    assert service.get_server(server_id).auto_approved_tools == ['create_issue']


def test_it_is_kept_per_user(service):
    mine = add_server(service, 'github', ['search'])
    theirs = add_server(service, 'github', ['search'], user_id='user-2')

    service.set_tool_auto_approved(mine, 'search', True)

    assert service.get_server(theirs).auto_approved_tools == []


def test_seeding_the_builtin_servers_again_keeps_it(service):
    service.ensure_builtin_servers(USER_ID)
    terminal = service.get_server_by_name(USER_ID, 'terminal_command')
    service.set_tool_auto_approved(terminal.id, 'terminal_command', True)

    service.ensure_builtin_servers(USER_ID)

    assert service.get_server(terminal.id).auto_approved_tools == ['terminal_command']


# --- Deciding ---

@pytest.mark.parametrize("tool_name, is_builtin, auto_approved, asks", [
    ("terminal_command", True, False, True),
    ("terminal_command", True, True, False),
    ("read_file", True, False, False),
    ("search", False, False, True),
    ("search", False, True, False),
])
def test_policy(tool_name, is_builtin, auto_approved, asks):
    policy = ToolsApprovalPolicy()

    assert policy.requires_approval(
        tool_name, is_builtin=is_builtin, auto_approved=auto_approved) is asks


def registry_for(service):
    registry = MCPRegistry(service, mcp_client=None, user_id=USER_ID)
    asyncio.run(registry.get_tools())
    return registry


def test_a_change_counts_on_the_next_call_of_a_running_task(service):
    server_id = add_server(service, 'github', ['search'])
    # The catalogue is taken once, when the task starts.
    registry = registry_for(service)
    assert not registry.is_auto_approved('search')

    service.set_tool_auto_approved(server_id, 'search', True)

    assert registry.is_auto_approved('search')


def test_a_server_reusing_a_tool_name_does_not_lend_its_permission(service):
    add_server(service, 'first', ['search'])
    second = add_server(service, 'second', ['search'])
    service.set_tool_auto_approved(second, 'search', True)

    # The model reaches "search" on the first server, which still asks.
    assert not registry_for(service).is_auto_approved('search')


def test_unknown_tool_is_not_allowed(service):
    assert not registry_for(service).is_auto_approved('nothing')


class Registry:
    def __init__(self, auto_approved):
        self.auto_approved = auto_approved
        self.calls = []

    def is_builtin_tool(self, name):
        return True

    def is_auto_approved(self, name):
        return self.auto_approved

    async def call_tool(self, name, args):
        self.calls.append(name)
        return SimpleNamespace(content=[SimpleNamespace(text="done")])


@pytest.mark.parametrize("auto_approved, asked", [(True, []), (False, ["terminal_command"])])
def test_an_allowed_tool_runs_without_a_card(auto_approved, asked):
    cards = []

    async def approve(name, args):
        cards.append(name)
        return True

    registry = Registry(auto_approved)
    adapter = ToolsAdapter(registry, ToolsApprovalPolicy(), approve_tool=approve)

    reply = asyncio.run(adapter.call_and_format("terminal_command", {"command": "ls"}))

    assert cards == asked
    assert registry.calls == ["terminal_command"]
    assert reply == "done"


def test_allowing_a_tool_mid_task_skips_the_card_on_its_next_call(service):
    service.ensure_builtin_servers(USER_ID)
    terminal = service.get_server_by_name(USER_ID, 'terminal_command')
    service.update_server(terminal.id, known_tools=[{'name': 'terminal_command'}])
    ran, cards = [], []

    class Client:
        async def call_tool(self, spec, name, args):
            ran.append(name)
            return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    async def approve(name, args):
        cards.append(name)
        return True

    async def scenario():
        registry = MCPRegistry(service, Client(), user_id=USER_ID)
        await registry.get_tools()          # once, as when the task starts
        adapter = ToolsAdapter(registry, ToolsApprovalPolicy(), approve_tool=approve)
        await adapter.call_and_format("terminal_command", {"command": "pwd"})
        service.set_tool_auto_approved(terminal.id, 'terminal_command', True)
        await adapter.call_and_format("terminal_command", {"command": "pwd"})

    asyncio.run(scenario())

    assert cards == ["terminal_command"]
    assert ran == ["terminal_command", "terminal_command"]


# --- Settings ---

def make_controller(service):
    view = FakeView()
    controller = MCPServersController(
        user=SimpleNamespace(id=USER_ID, username='miwa'), model=service, view=view,
        mcp_registry=None)
    controller.refresh()
    return controller, view


def tool(view, server_name, tool_name):
    return next(t for t in view.row(server_name)['tool_list'] if t['name'] == tool_name)


def test_settings_list_each_tool_with_how_it_asks(service):
    service.ensure_builtin_servers(USER_ID)
    filesystem = service.get_server_by_name(USER_ID, 'filesystem_command')
    service.update_server(filesystem.id, known_tools=[
        {'name': 'read_file', 'description': 'Read a file'},
        {'name': 'write_file', 'description': 'Write a file'}])
    add_server(service, 'github', ['search'])

    _, view = make_controller(service)

    assert tool(view, 'filesystem_command', 'read_file')['asks_by_default'] is False
    assert tool(view, 'filesystem_command', 'write_file')['asks_by_default'] is True
    assert tool(view, 'github', 'search')['asks_by_default'] is True
    assert tool(view, 'github', 'search')['auto_approved'] is False


def test_switching_a_tool_in_settings_saves_it(service):
    server_id = add_server(service, 'github', ['search'])
    _, view = make_controller(service)

    view.auto_approve_changed.emit(server_id, 'search', True)

    assert service.get_server(server_id).auto_approved_tools == ['search']
    assert tool(view, 'github', 'search')['auto_approved'] is True

    view.auto_approve_changed.emit(server_id, 'search', False)

    assert tool(view, 'github', 'search')['auto_approved'] is False


def test_settings_mark_a_tool_another_server_provides(service):
    add_server(service, 'first', ['search'])
    add_server(service, 'second', ['search'])

    _, view = make_controller(service)

    assert tool(view, 'first', 'search')['shadowed_by'] is None
    assert tool(view, 'second', 'search')['shadowed_by'] == 'first'
