"""Screen control is off until the user agrees, in Settings, to it running
without asking - and then it does."""
import asyncio
import os
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject, Signal

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from agent.mcp_probe import ProbeResult  # noqa: E402
from agent.mcp_registry import MCPRegistry  # noqa: E402
from core.services import MCPServerService  # noqa: E402
from db.database import MCPServer_DB  # noqa: E402
from interface.gui.controller import MCPServersController  # noqa: E402
from mcp_tools.input_control import server as input_server  # noqa: E402
from tests.unit.test_mcp_servers_settings import FakeRegistry, FakeView, settle  # noqa: E402

USER_ID = "user-1"
SCREEN_TOOLS = {'screenshot_command': ['make_screenshot', 'find_on_screen'],
                'input_control': ['click', 'type_text']}


@pytest.fixture
def service(tmp_path):
    db = MCPServer_DB(db_name=str(tmp_path / "test.sqlite3"))
    db.create_table()
    service = MCPServerService(mcp_server_db=db)
    service.ensure_builtin_servers(USER_ID)
    # As a past check would have left them: switched on, tools known.
    for server in service.get_user_servers(USER_ID):
        tools = SCREEN_TOOLS.get(server.name, [f'{server.name}_tool'])
        service.update_server(server.id, last_status='ok', known_tools=[
            {'name': tool, 'description': '', 'inputSchema': {}} for tool in tools])
    return service


def offered(service) -> set[str]:
    specs, _ = service.get_tool_catalogue(USER_ID)
    return {spec['name'] for spec in specs}


def screen_servers(service):
    return {s.name: s for s in service.screen_control_servers(USER_ID)}


# --- MCPServerService ---

def test_screen_tools_are_not_offered_until_the_user_agrees(service):
    # Switched on, as in a database from before the consent existed.
    assert all(s.is_enabled for s in screen_servers(service).values())

    assert not service.is_screen_control_allowed(USER_ID)
    assert offered(service).isdisjoint({'click', 'type_text', 'make_screenshot', 'find_on_screen'})
    assert 'web_search_tool' in offered(service)


def test_agreeing_offers_them_and_they_run_without_asking(service):
    service.set_screen_control_allowed(USER_ID, True)

    assert service.is_screen_control_allowed(USER_ID)
    assert {'click', 'type_text', 'make_screenshot', 'find_on_screen'} <= offered(service)
    registry = MCPRegistry(service, mcp_client=None, user_id=USER_ID)
    asyncio.run(registry.get_tools())
    assert registry.is_auto_approved('click')
    assert registry.is_auto_approved('find_on_screen')
    # Other servers' tools are not swept along.
    assert not registry.is_auto_approved('terminal_command_tool')


def test_taking_it_back_switches_them_off(service):
    service.set_screen_control_allowed(USER_ID, True)

    service.set_screen_control_allowed(USER_ID, False)

    assert not service.is_screen_control_allowed(USER_ID)
    assert not any(s.is_enabled for s in screen_servers(service).values())
    assert 'click' not in offered(service)


def test_consent_is_kept_per_user(service):
    service.ensure_builtin_servers("someone-else")
    service.set_screen_control_allowed(USER_ID, True)

    assert not service.is_screen_control_allowed("someone-else")


def test_an_existing_database_gets_the_column(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE mcp_servers (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            transport TEXT NOT NULL, command TEXT, args TEXT, env TEXT, url TEXT,
            headers TEXT, description TEXT, is_builtin INTEGER DEFAULT 0,
            is_enabled INTEGER DEFAULT 1, created_at TEXT)""")
        conn.execute("INSERT INTO mcp_servers (id, user_id, name, transport, is_builtin) "
                     "VALUES ('s1', 'u', 'input_control', 'stdio', 1)")

    MCPServer_DB(db_name=path).create_table()

    service = MCPServerService(mcp_server_db=MCPServer_DB(db_name=path))
    assert service.get_server('s1').runs_without_asking is False
    service.set_screen_control_allowed('u', True)
    assert service.get_server('s1').runs_without_asking is True


# --- MCPServersController ---

class FakeScreenView(QObject):
    allowed_changed = Signal(bool)
    check_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.allowed = None
        self.servers = []

    def set_allowed(self, allowed):
        self.allowed = allowed

    def show_servers(self, servers):
        self.servers = servers

    def row(self, name):
        return next(s for s in self.servers if s['name'] == name)


async def ok_probe(*args, **kwargs):
    return ProbeResult(ok=True, code='ok', message='', tools=('click',),
                       tool_specs=({'name': 'click', 'inputSchema': {}},))


def run_consent(service, *choices):
    async def scenario():
        view, screen_view, registry = FakeView(), FakeScreenView(), FakeRegistry()
        # Kept in a variable: once collected, its slots are disconnected.
        controller = MCPServersController(  # noqa: F841
            user=SimpleNamespace(id=USER_ID, username='miwa'), model=service,
            view=view, mcp_registry=registry, screen_view=screen_view)
        shown_at_start = screen_view.allowed
        # Settings opened, as showEvent reports it.
        view.opened.emit()
        with patch('agent.mcp_probe.probe', side_effect=ok_probe):
            for allowed in choices:
                screen_view.allowed_changed.emit(allowed)
                await settle()
        return SimpleNamespace(view=view, screen_view=screen_view, registry=registry,
                               shown_at_start=shown_at_start)
    return asyncio.run(scenario())


def test_the_stored_choice_is_shown(service):
    service.set_screen_control_allowed(USER_ID, True)

    assert run_consent(service).shown_at_start is True


def test_allowing_in_settings_checks_servers_never_checked(service):
    for server in screen_servers(service).values():
        service.update_server(server.id, last_status=None)

    result = run_consent(service, True)

    assert result.screen_view.allowed is True
    for name in SCREEN_TOOLS:
        row = result.screen_view.row(name)
        assert row['status'] == 'ok'
        assert all(tool['locked'] and tool['auto_approved'] for tool in row['tool_list'])


def test_screen_servers_are_listed_under_the_consent_box(service):
    result = run_consent(service)

    assert {row['name'] for row in result.screen_view.servers} == set(SCREEN_TOOLS)
    assert set(SCREEN_TOOLS).isdisjoint(row['name'] for row in result.view.servers)
    assert 'web_search' in {row['name'] for row in result.view.servers}


def test_checking_a_screen_server_from_its_row(service):
    server_id = screen_servers(service)['input_control'].id
    service.update_server(server_id, last_status='error', last_error_code='spawn_failed')

    async def scenario():
        screen_view = FakeScreenView()
        controller = MCPServersController(  # noqa: F841
            user=SimpleNamespace(id=USER_ID, username='miwa'), model=service,
            view=FakeView(), mcp_registry=FakeRegistry(), screen_view=screen_view)
        with patch('agent.mcp_probe.probe', side_effect=ok_probe):
            screen_view.check_requested.emit(server_id)
            await settle()

    asyncio.run(scenario())

    assert service.get_server(server_id).last_status == 'ok'


def test_taking_it_back_in_settings_stops_the_servers(service):
    result = run_consent(service, True, False)

    assert sorted(result.registry.stopped) == sorted(s.id for s in screen_servers(service).values())
    assert result.screen_view.row('input_control')['status'] == 'needs_consent'
    assert result.screen_view.allowed is False


# --- Stopping it ---

def test_mouse_in_a_corner_stops_screen_control_until_it_restarts():
    with patch.object(input_server, "_stopped_by_user", False), \
            patch.object(input_server, "missing_input_access", return_value=None), \
            patch.object(input_server.pyautogui, "size", return_value=(1512, 982)), \
            patch.object(input_server.pyautogui, "hotkey"), \
            patch.object(input_server.pyautogui, "click",
                         side_effect=input_server.pyautogui.FailSafeException("corner")) as click:
        stopped = asyncio.run(input_server.click(100, 100))
        # The mouse has left the corner; nothing goes through all the same.
        click.side_effect = None
        click.reset_mock()
        later_click = asyncio.run(input_server.click(200, 200))
        later_keys = asyncio.run(input_server.press_keys("enter"))

    assert stopped.startswith("Stopped: the user moved the mouse into a corner")
    assert later_click == stopped and later_keys == stopped
    click.assert_not_called()
