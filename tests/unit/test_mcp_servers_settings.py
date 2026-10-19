import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from PySide6.QtCore import QObject, Signal

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from agent.mcp_probe import ProbeResult  # noqa: E402
from core.crypto import SecretBox, secret_ref  # noqa: E402
from core.services import MCPServerService, SecretService  # noqa: E402
from db.database import MCPServer_DB, Secret_DB  # noqa: E402
from interface.gui.controller import MCPServersController, parse_server_form  # noqa: E402

USER_ID = "user-1"


@pytest.fixture
def secrets(tmp_path):
    db = Secret_DB(db_name=str(tmp_path / "test.sqlite3"))
    db.create_table()
    return SecretService(secret_db=db, secret_box=SecretBox(key=Fernet.generate_key()))


@pytest.fixture
def service(tmp_path, secrets):
    db = MCPServer_DB(db_name=str(tmp_path / "test.sqlite3"))
    db.create_table()
    return MCPServerService(mcp_server_db=db, secret_service=secrets)


def stdio_form(**overrides):
    form = {'name': 'github', 'transport': 'stdio',
            'command': 'npx -y "@scope/server github"', 'env': '',
            'url': '', 'headers': '', 'description': ''}
    form.update(overrides)
    return form


# --- parse_server_form ---

def test_parse_stdio_splits_command_and_reads_env():
    server = parse_server_form(stdio_form(env="# comment\nGITHUB_TOKEN = abc=def\n\nDEBUG=1"))

    assert server['command'] == 'npx'
    assert server['args'] == ['-y', '@scope/server github']
    assert server['env'] == {'GITHUB_TOKEN': 'abc=def', 'DEBUG': '1'}
    assert server['description'] is None


def test_parse_http_reads_headers():
    server = parse_server_form(stdio_form(
        transport='http', url=' https://example.com/mcp ',
        headers='Authorization: Bearer x:y'))

    assert server['url'] == 'https://example.com/mcp'
    assert server['headers'] == {'Authorization': 'Bearer x:y'}
    assert 'command' not in server


@pytest.mark.parametrize("overrides, message", [
    ({'name': '  '}, "Name is required"),
    ({'name': 'my server'}, "Name may only contain"),
    ({'name': 'a.b'}, "Name may only contain"),
    ({'command': '   '}, "Command is required"),
    ({'command': 'npx "unclosed'}, "Command:"),
    ({'env': 'NO_EQUALS_SIGN'}, "Environment"),
    ({'env': '1BAD=x'}, "Environment"),
    ({'env': 'A=1\nA=2'}, "set twice"),
    ({'transport': 'http', 'url': 'example.com'}, "URL must start"),
    ({'transport': 'http', 'url': 'https://x', 'headers': 'Bad Header: 1'}, "Headers"),
    ({'transport': None}, "Choose the server type"),
])
def test_parse_rejects_bad_input(overrides, message):
    with pytest.raises(ValueError, match=message):
        parse_server_form(stdio_form(**overrides))


# --- MCPServerService: credentials go to the secrets table ---

def test_add_user_server_stores_env_values_encrypted(service, secrets):
    server_id = service.add_user_server(
        USER_ID, name='github', transport='stdio', command='npx', args=[],
        env={'GITHUB_TOKEN': 'ghp_secret', 'MINE': '${secret:shared}', 'EMPTY': ''})

    server = service.get_server(server_id)
    assert server.env == {'GITHUB_TOKEN': secret_ref('github.env.GITHUB_TOKEN'),
                          'MINE': '${secret:shared}', 'EMPTY': ''}
    assert secrets.get_secret(USER_ID, 'github.env.GITHUB_TOKEN') == 'ghp_secret'
    assert 'ghp_secret' not in str(service.mcp_server_db.get_server_by_id(server_id))


def test_add_user_server_stores_header_values_encrypted(service, secrets):
    server_id = service.add_user_server(
        USER_ID, name='remote', transport='http', url='https://x',
        headers={'Authorization': 'Bearer t0ken'})

    assert service.get_server(server_id).headers == {
        'Authorization': secret_ref('remote.header.Authorization')}
    assert secrets.get_secret(USER_ID, 'remote.header.Authorization') == 'Bearer t0ken'


def test_duplicate_name_does_not_overwrite_existing_credentials(service, secrets):
    service.add_user_server(USER_ID, name='github', transport='stdio',
                            command='npx', env={'TOKEN': 'original'})

    again = service.add_user_server(USER_ID, name='github', transport='stdio',
                                    command='npx', env={'TOKEN': 'replacement'})

    assert again is None
    assert secrets.get_secret(USER_ID, 'github.env.TOKEN') == 'original'


def test_delete_server_removes_only_its_own_secrets(service, secrets):
    secrets.set_secret(USER_ID, 'shared', 'kept')
    server_id = service.add_user_server(
        USER_ID, name='github', transport='stdio', command='npx',
        env={'TOKEN': 'gone', 'OTHER': '${secret:shared}'})

    assert service.delete_server(server_id)

    assert secrets.get_secret(USER_ID, 'github.env.TOKEN') is None
    assert secrets.get_secret(USER_ID, 'shared') == 'kept'


def test_credentials_without_secret_service_are_refused(tmp_path):
    db = MCPServer_DB(db_name=str(tmp_path / "test.sqlite3"))
    db.create_table()
    service = MCPServerService(mcp_server_db=db)

    with pytest.raises(RuntimeError):
        service.add_user_server(USER_ID, name='x', transport='stdio',
                                command='npx', env={'TOKEN': 'plain'})
    assert service.get_user_servers(USER_ID) == []


# --- MCPServersController ---

class FakeView(QObject):
    add_requested = Signal(dict)
    delete_requested = Signal(str)
    enabled_changed = Signal(str, bool)
    check_requested = Signal(str)
    opened = Signal()

    def __init__(self):
        super().__init__()
        self.servers = []
        self.form_error = None
        self.form_closed = False

    def show_servers(self, servers):
        self.servers = servers

    def show_form_error(self, text):
        self.form_error = text

    def close_form(self):
        self.form_closed = True

    def row(self, name):
        return next(s for s in self.servers if s['name'] == name)


class FakeRegistry:
    def __init__(self):
        self.stopped = []

    async def stop_server(self, server_id):
        self.stopped.append(server_id)
        return True


async def ok_probe(*args, **kwargs):
    return ProbeResult(ok=True, code='ok', message='',
                       tools=('search',),
                       tool_specs=({'name': 'search', 'inputSchema': {}},))


async def failing_probe(*args, **kwargs):
    return ProbeResult(ok=False, code='spawn_failed', message='no such file\nmore')


async def settle():
    """Lets the checks the controller started run to completion."""
    current = asyncio.current_task()
    while pending := [t for t in asyncio.all_tasks() if t is not current]:
        await asyncio.gather(*pending)


def make_controller(service):
    view = FakeView()
    registry = FakeRegistry()
    user = SimpleNamespace(id=USER_ID, username='miwa')
    controller = MCPServersController(user=user, model=service, view=view,
                                      mcp_registry=registry)
    return controller, view, registry


def test_add_checks_the_new_server(service):
    async def scenario():
        controller, view, _ = make_controller(service)
        with patch('agent.mcp_probe.probe', side_effect=ok_probe):
            view.add_requested.emit(stdio_form())
            assert view.row('github')['status'] == 'checking'
            await settle()
        return view

    view = asyncio.run(scenario())

    assert view.form_closed
    row = view.row('github')
    assert row['status'] == 'ok'
    assert row['tools'] == 1
    assert row['detail'] == 'npx -y @scope/server github'


def test_add_with_taken_name_reports_error(service):
    service.add_user_server(USER_ID, name='github', transport='stdio', command='npx')

    async def scenario():
        controller, view, _ = make_controller(service)
        view.add_requested.emit(stdio_form())
        return view

    view = asyncio.run(scenario())

    assert 'already exists' in view.form_error
    assert not view.form_closed


def test_add_with_invalid_form_reports_error(service):
    async def scenario():
        controller, view, _ = make_controller(service)
        view.add_requested.emit(stdio_form(command=''))
        return view

    view = asyncio.run(scenario())

    assert view.form_error == "Command is required."
    assert service.get_user_servers(USER_ID) == []


def test_failed_check_shows_error_and_disables(service):
    server_id = service.add_user_server(USER_ID, name='github', transport='stdio', command='npx')

    async def scenario():
        controller, view, _ = make_controller(service)
        with patch('agent.mcp_probe.probe', side_effect=failing_probe):
            view.check_requested.emit(server_id)
            await settle()
        return view

    view = asyncio.run(scenario())

    row = view.row('github')
    assert row['status'] == 'error'
    assert row['error_code'] == 'spawn_failed'
    assert not row['is_enabled']


def test_disabling_stops_the_running_server(service):
    server_id = service.add_user_server(USER_ID, name='github', transport='stdio', command='npx')

    async def scenario():
        controller, view, registry = make_controller(service)
        view.enabled_changed.emit(server_id, False)
        await settle()
        return view, registry

    view, registry = asyncio.run(scenario())

    assert registry.stopped == [server_id]
    assert view.row('github')['status'] == 'off'
    assert not service.get_server(server_id).is_enabled


def test_enabling_a_never_checked_server_checks_it(service):
    server_id = service.add_user_server(USER_ID, name='github', transport='stdio', command='npx')
    service.set_server_enabled(server_id, False)

    async def scenario():
        controller, view, _ = make_controller(service)
        with patch('agent.mcp_probe.probe', side_effect=failing_probe):
            view.enabled_changed.emit(server_id, True)
            await settle()
        return view

    view = asyncio.run(scenario())

    # The check failed, so the server is switched back off.
    assert view.row('github')['status'] == 'error'
    assert not service.get_server(server_id).is_enabled


def test_delete_stops_and_removes_server(service):
    server_id = service.add_user_server(USER_ID, name='github', transport='stdio', command='npx')

    async def scenario():
        controller, view, registry = make_controller(service)
        view.delete_requested.emit(server_id)
        await settle()
        return view, registry

    view, registry = asyncio.run(scenario())

    assert registry.stopped == [server_id]
    assert service.get_server(server_id) is None
    assert view.servers == []


def test_builtin_server_is_not_deleted(service):
    service.ensure_builtin_servers(USER_ID)
    builtin = service.get_user_servers(USER_ID)[0]

    async def scenario():
        controller, view, registry = make_controller(service)
        view.delete_requested.emit(builtin.id)
        await settle()
        return registry

    registry = asyncio.run(scenario())

    assert service.get_server(builtin.id) is not None
    assert registry.stopped == []


def test_disconnected_controller_ignores_view_and_cancels_checks(service):
    server_id = service.add_user_server(USER_ID, name='github', transport='stdio', command='npx')

    async def hanging_probe(*args, **kwargs):
        await asyncio.sleep(3600)

    async def scenario():
        controller, view, _ = make_controller(service)
        with patch('agent.mcp_probe.probe', side_effect=hanging_probe):
            controller.check_all()
            await asyncio.sleep(0)
            controller.disconnect_view()
            await asyncio.gather(*controller._check_tasks, return_exceptions=True)
        view.servers = ['untouched']
        view.opened.emit()
        return view

    view = asyncio.run(scenario())

    assert view.servers == ['untouched']
    assert service.get_server(server_id).last_status is None