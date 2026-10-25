from PySide6.QtCore import Signal, QObject
from core.models import User, MCPServer
from interface.gui.view import RegistrationPage, LoginPage, ChatPage, SettingsPage, AppWindow, MCPServersSection, ScreenControlSection
from core.services import AuthService, ChatService, MessageService, AIClientService, MCPServerService, is_screen_control, needs_consent
from interface.gui.worker import AIWorker, STOPPED_OUTPUT
from interface.gui.mcp_tools_approval import HumanToolApproval
from agent.tools_policy import ToolsApprovalPolicy
import asyncio
import json
import re

# Server names also prefix the names of their secrets, which may not contain
# anything else - and a dot is what separates the parts of those names.
_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")

# What a pasted server entry may hold, by transport. Configs written for other
# clients can carry more (cwd, timeout, ...); those are refused rather than
# dropped, since a server started without them may not behave as expected.
_ENTRY_KEYS = {
    MCPServer.STDIO: {'type', 'command', 'args', 'env', 'description'},
    MCPServer.HTTP: {'type', 'url', 'headers', 'description'},
}
# Values of "type" as different clients spell them.
_TYPE_NAMES = {
    'stdio': MCPServer.STDIO,
    'http': MCPServer.HTTP,
    'streamable-http': MCPServer.HTTP,
    'streamableHttp': MCPServer.HTTP,
}
_NEEDS_COMMAND_OR_URL = ('The JSON needs a "command" (local server) '
                         'or a "url" (remote server).')
# Placeholders other clients fill in before starting a server - VS Code's
# ${input:...} asks the user, ${env:...} and ${workspaceFolder} read its own
# state. Nothing here fills them in, so one would reach the server as literal
# text. ${secret:NAME} is this app's own reference and is left alone.
_FOREIGN_PLACEHOLDER_RE = re.compile(r"\$\{(?!secret:)[^}]*\}")


class ViewManager:
    """Owns the single AppWindow and switches which page its QStackedWidget
    shows. Login, registration and chat are all pages of that one window, and
    naming a new chat happens in an inline cell, so the app has no popups."""

    def __init__(self, app_window: AppWindow, main_view: ChatPage, login_view: LoginPage,
                 registration_view: RegistrationPage, settings_view: SettingsPage):
        self.app_window = app_window
        self.login_view = login_view
        self.registration_view = registration_view
        self.main_view = main_view
        self.settings_view = settings_view

        self.app_window.add_page(self.login_view)
        self.app_window.add_page(self.registration_view)
        self.app_window.add_page(self.main_view)
        self.app_window.add_page(self.settings_view)

        self.login_view.switch_to_registration.connect(self.show_registration)
        self.registration_view.switch_to_login.connect(self.show_login)
        self.main_view.logout_requested.connect(self.handle_logout)
        self.main_view.settings_requested.connect(self.show_settings)
        self.settings_view.close_requested.connect(self.show_main_window)

    def show_login(self):
        self.app_window.show_page(self.login_view)

    def show_registration(self):
        self.app_window.show_page(self.registration_view)

    def show_main_window(self):
        self.app_window.show_page(self.main_view)

    def show_settings(self):
        self.app_window.show_page(self.settings_view)

    def handle_logout(self):
        # The chat page outlives the login: the chat open on it would still be
        # showing when the next user logs in. Their login refills the chat
        # list, but nothing reopens the right-hand side.
        self.main_view.clear_chat_view()
        self.app_window.show_page(self.login_view)


class RegistrationController(QObject):
    def __init__(self, model: AuthService, view: RegistrationPage):
        super().__init__()
        self._model = model
        self._view = view

        self._view.registration_submitted.connect(self.handle_registration)

    def handle_registration(self, user_data: dict):
        """
        Processes the data received from the registration window.
        """
        success, message = self._model.register_user(
            username=user_data["username"],
            email=user_data["email"],
            password=user_data["password"]
        )

        if success:
            self._view.show_message(message, is_error=False)

        else:
            self._view.show_message(message, is_error=True)


class LoginController(QObject):
    login_successful = Signal(User)

    def __init__(self, model: AuthService, view: LoginPage):
        super().__init__()
        self._model = model
        self._view = view

        self._view.login_submitted.connect(self.handle_login)

    def handle_login(self, user_data: dict):
        """
        Processes the data received from the login window.
        """
        success, result = self._model.login_user(
            username=user_data["username"],
            password=user_data["password"]
        )

        if success:
            user_object = result
            self.login_successful.emit(user_object)

        else:
            self._view.show_message(result, is_error=True)


class MainWindowController(QObject):
    def __init__(self, user: User, model: ChatService, view: ChatPage):
        super().__init__()
        self._model = model
        self._view = view
        self._user = user

        self._view.new_chat_requested.connect(self.handle_create_new_chat)
        self._view.chat_delete_requested.connect(self.handle_delete_chat)
        self._view.chat_shown.connect(self.show_workspace)
        self._view.workspace_change_requested.connect(self.handle_workspace_change)

    def disconnect_view(self):
        """A fresh controller is built on every login, so the previous one has
        to let go of the (long-lived) view first - otherwise a second login
        would handle each action twice."""
        self._view.new_chat_requested.disconnect(self.handle_create_new_chat)
        self._view.chat_delete_requested.disconnect(self.handle_delete_chat)
        self._view.chat_shown.disconnect(self.show_workspace)
        self._view.workspace_change_requested.disconnect(self.handle_workspace_change)

    def update_chat_list_in_view(self):
        chat_objects = self._model.get_all_user_chats(user_id=self._user.id)
        chats_for_view = [{'id': chat.id, 'title': chat.title}
                          for chat in chat_objects]
        self._view.update_chats_list(chats_for_view)

    def handle_create_new_chat(self, chat_title: str):
        self._model.create_new_chat(
            user_id=self._user.id, chat_title=chat_title)

        self.update_chat_list_in_view()

    def handle_delete_chat(self, chat_id: str):
        if not self._model.delete_chat(chat_id=chat_id):
            print(f"Chat {chat_id} could not be deleted.")
            return

        if self._view.current_chat_id == chat_id:
            self._view.clear_chat_view()

        self.update_chat_list_in_view()

    def show_workspace(self, chat_id: str):
        self._view.show_workspace(
            chat_id,
            self._model.get_workspace(chat_id),
            self._model.is_default_workspace(chat_id))

    def handle_workspace_change(self, chat_id: str, folder: str):
        """An empty folder puts the chat back on the default one."""
        try:
            self._model.set_workspace(chat_id, folder or None)
        except ValueError as e:
            self._view.show_workspace_error(str(e))
            return
        self.show_workspace(chat_id)


class MessageController(QObject):
    def __init__(self, model: MessageService, view: ChatPage):
        super().__init__()
        self._model = model
        self._view = view

        self._view.chat_selected.connect(self.show_messages)

    def show_messages(self, chat_id):
        messages = self._model.get_messages_from_chat(chat_id=chat_id)
        message_data_for_view = []
        for msg_obj in messages:
            message_data_for_view.append({
                'input': msg_obj.input,
                'output': msg_obj.output
            })

        self._view.show_chat(
            chat_id=chat_id, message_data=message_data_for_view)


class AIClientController(QObject):
    """Runs one prompt at a time. The task belongs to the chat it was sent
    from and keeps running while other chats are opened: its answer goes to
    that chat only, and its approval cards come back when it is reopened."""

    def __init__(self, model: AIClientService, view: ChatPage, mcp_registry,
                 chat_model: ChatService | None = None):
        super().__init__()
        self._model = model
        self._view = view
        self._mcp_registry = mcp_registry
        # Looks up each chat's workspace folder; without it every task works
        # in the default one.
        self._chat_model = chat_model
        self._tool_approval = HumanToolApproval(view=self._view)
        self._approval_policy = ToolsApprovalPolicy()
        # Kept so the task can be stopped; asyncio itself only holds a weak
        # reference to it.
        self._task: asyncio.Task | None = None
        self._task_chat_id: str | None = None
        self._view.send_input.connect(self.handle_prompt)
        self._view.stop_requested.connect(self.stop)
        self._view.chat_shown.connect(self.handle_chat_shown)
        self._view.chat_delete_requested.connect(self.handle_chat_deleted)
        # A task left running would keep acting after logout - and against the
        # next user's servers and secrets once they log in.
        self._view.logout_requested.connect(self.stop)

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def handle_prompt(self, chat_id, user_input):
        if self.is_running:
            return
        self._task_chat_id = chat_id
        self._view.set_busy_chat(chat_id)

        self.worker = AIWorker(
            self._model,
            chat_id,
            user_input,
            mcp_registry=self._mcp_registry,
            approve_tool=self._tool_approval.for_chat(chat_id),
            tools_approval_policy=self._approval_policy,
            workspace=(self._chat_model.get_workspace(chat_id)
                       if self._chat_model is not None else None),
        )

        self.worker.finished.connect(
            lambda response, cid=chat_id: self.handle_ai_response(cid, response))
        self.worker.error.connect(
            lambda message, cid=chat_id: self.handle_ai_error(cid, message))
        self.worker.stopped.connect(
            lambda cid=chat_id: self.handle_stopped(cid))

        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.worker.stopped.connect(self.worker.deleteLater)
        self._task = asyncio.create_task(self.worker.run())

    def stop(self):
        """Stops the running task right where it is - waiting for the model,
        for an approval, or in the middle of a tool call."""
        if not self.is_running or self._task.cancelling():
            return
        self._task.cancel()

    def handle_chat_shown(self, chat_id):
        if chat_id == self._task_chat_id:
            self._tool_approval.show_chat(chat_id)

    def handle_chat_deleted(self, chat_id):
        if chat_id == self._task_chat_id:
            self.stop()

    def _finish(self):
        self._task = None
        self._task_chat_id = None
        self._tool_approval.clear()
        self._view.set_busy_chat(None)

    def _reply_in(self, chat_id, text):
        # The user may have opened another chat meanwhile; the answer is
        # saved with its own chat and shows up when that one is opened.
        if self._view.current_chat_id == chat_id:
            self._view.add_assistant_message(text)

    def handle_ai_response(self, chat_id, response_dict):
        self._finish()

        try:

            if response_dict and 'output' in response_dict:
                assistant_output = response_dict['output']
                self._reply_in(chat_id, assistant_output)
            else:
                self._reply_in(chat_id, "Sorry, I received an invalid response.")
        except Exception as e:
            self.handle_ai_error(chat_id, f"Error processing response: {e}")

    def handle_ai_error(self, chat_id, error_message):
        self._finish()

        self._reply_in(chat_id, f"Sorry, an error occurred: {error_message}")

    def handle_stopped(self, chat_id):
        self._finish()
        self._reply_in(chat_id, STOPPED_OUTPUT)


def _server_entry(data) -> tuple[str | None, dict]:
    """Finds the one server in the pasted JSON, along with the name it is
    filed under if it has one. Docs usually show a server inside
    {"mcpServers": {"name": {...}}} - VS Code says "servers" - so both the
    wrapper and the name level are optional."""
    if not isinstance(data, dict):
        raise ValueError("The JSON must be an object: { ... }.")
    for wrapper in ('mcpServers', 'servers'):
        if isinstance(data.get(wrapper), dict):
            data = data[wrapper]
            break
    if 'command' in data or 'url' in data:
        return None, data

    servers = [key for key, value in data.items() if isinstance(value, dict)]
    if len(servers) > 1:
        raise ValueError(f"The JSON has {len(servers)} servers "
                         f"({', '.join(servers)}) - add them one at a time.")
    if len(servers) == 1 and len(data) == 1:
        return servers[0], data[servers[0]]
    raise ValueError(_NEEDS_COMMAND_OR_URL)


def _strings(value):
    """Every string inside a pasted value, however deeply nested."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _string_map(value, key_re: re.Pattern, what: str) -> dict:
    """Checks an env or headers object. A value left unquoted is refused
    rather than converted, so what gets stored is exactly what was pasted."""
    if not isinstance(value, dict):
        raise ValueError(f'{what} must be an object: {{"NAME": "value"}}.')
    for key, item in value.items():
        if not key_re.match(key):
            raise ValueError(f'{what}: "{key}" is not a valid name.')
        if not isinstance(item, str):
            raise ValueError(
                f'{what}: the value of "{key}" must be a string - put it in quotes.')
    return dict(value)


def parse_server_form(form: dict) -> dict:
    """Turns the add-server form - a name and the server's JSON config, in
    the shape MCP servers document it - into the arguments of
    MCPServerService.add_user_server. Raises ValueError with a message meant
    for the user."""
    text = form.get('config', '').strip()
    if not text:
        raise ValueError("Paste the server's JSON config.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON: {e.msg} (line {e.lineno}, column {e.colno}).") from None
    filed_name, entry = _server_entry(data)

    typed_name = form.get('name', '').strip()
    name = typed_name or (filed_name or '').strip()
    if not name:
        raise ValueError("Name is required.")
    if not _SERVER_NAME_RE.match(name):
        if not typed_name:
            raise ValueError(f'The JSON names the server "{name}" - type a Name '
                             'using only letters, digits, _ and -.')
        raise ValueError("Name may only contain letters, digits, _ and -.")

    if 'command' in entry and 'url' in entry:
        raise ValueError('Give either "command" or "url", not both.')
    if 'command' not in entry and 'url' not in entry:
        raise ValueError(_NEEDS_COMMAND_OR_URL)
    transport = MCPServer.HTTP if 'url' in entry else MCPServer.STDIO

    kind = entry.get('type')
    if kind == 'sse':
        # The client only speaks streamable HTTP.
        raise ValueError('SSE servers are not supported, only streamable HTTP - '
                         'many servers offer it too, often at a URL ending in /mcp.')
    if kind is not None and (not isinstance(kind, str) or kind not in _TYPE_NAMES):
        raise ValueError(f'Unknown "type": {json.dumps(kind)}.')
    if kind is not None and _TYPE_NAMES[kind] != transport:
        given = 'url' if transport == MCPServer.HTTP else 'command'
        raise ValueError(f'"type": "{kind}" does not fit a server with a "{given}".')

    unsupported = sorted(set(entry) - _ENTRY_KEYS[transport])
    if unsupported:
        what = 'a remote server' if transport == MCPServer.HTTP else 'a local command'
        raise ValueError(f"Not supported for {what}: "
                         + ", ".join(f'"{key}"' for key in unsupported) + ".")
    for text in _strings(entry):
        placeholder = _FOREIGN_PLACEHOLDER_RE.search(text)
        if placeholder:
            raise ValueError(
                f'"{placeholder.group()}" is a placeholder another app fills in - '
                'put the actual value in its place.')

    description = entry.get('description') or ''
    if not isinstance(description, str):
        raise ValueError('"description" must be a string.')
    server = {
        'name': name,
        'transport': transport,
        'description': description.strip() or None,
    }

    if transport == MCPServer.STDIO:
        command = entry['command']
        if not isinstance(command, str) or not command.strip():
            raise ValueError('"command" must be a non-empty string.')
        args = entry.get('args', [])
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError('"args" must be a list of strings.')
        server['command'] = command.strip()
        server['args'] = args
        server['env'] = _string_map(entry.get('env', {}), _ENV_KEY_RE, '"env"')
    else:
        url = entry['url']
        if not isinstance(url, str) or not url.strip().startswith(('http://', 'https://')):
            raise ValueError('"url" must start with http:// or https://.')
        server['url'] = url.strip()
        server['headers'] = _string_map(
            entry.get('headers', {}), _HEADER_NAME_RE, '"headers"')

    return server


class MCPServersController(QObject):
    """Drives the MCP servers section of settings. Built on every login, like
    MainWindowController, since everything it shows belongs to one user - and
    it also runs the connection checks, so the section can show which servers
    are being checked right now. It also drives the screen-control consent,
    since what that does is switch two of those servers on or off."""

    def __init__(self, user: User, model: MCPServerService, view: MCPServersSection, mcp_registry,
                 screen_view: ScreenControlSection | None = None):
        super().__init__()
        self._user = user
        self._model = model
        self._view = view
        self._screen_view = screen_view
        self._mcp_registry = mcp_registry
        # Tells which tools ask before running unless the user allowed them -
        # the same rule the chat applies.
        self._approval_policy = ToolsApprovalPolicy()
        self._active = True
        self._checking: set[str] = set()
        # asyncio only holds weak references to tasks, so they are kept here.
        self._check_tasks: set[asyncio.Task] = set()
        self._stop_tasks: set[asyncio.Task] = set()

        self._view.opened.connect(self.refresh)
        self._view.add_requested.connect(self.handle_add)
        self._view.delete_requested.connect(self.handle_delete)
        self._view.enabled_changed.connect(self.handle_enabled_changed)
        self._view.check_requested.connect(self.handle_check)
        self._view.auto_approve_changed.connect(self.handle_auto_approve_changed)
        if self._screen_view is not None:
            self._screen_view.allowed_changed.connect(self.handle_screen_control_changed)
            self._screen_view.check_requested.connect(self.handle_check)
            self._screen_view.set_allowed(self._model.is_screen_control_allowed(self._user.id))

    def disconnect_view(self):
        """Lets go of the (long-lived) view before the next login builds a new
        controller. Checks still running are for this user, so they are
        cancelled rather than left to paint over the next user's list."""
        self._active = False
        self._view.opened.disconnect(self.refresh)
        self._view.add_requested.disconnect(self.handle_add)
        self._view.delete_requested.disconnect(self.handle_delete)
        self._view.enabled_changed.disconnect(self.handle_enabled_changed)
        self._view.check_requested.disconnect(self.handle_check)
        self._view.auto_approve_changed.disconnect(self.handle_auto_approve_changed)
        if self._screen_view is not None:
            self._screen_view.allowed_changed.disconnect(self.handle_screen_control_changed)
            self._screen_view.check_requested.disconnect(self.handle_check)
        for task in list(self._check_tasks):
            task.cancel()

    def refresh(self):
        if not self._active:
            return
        servers = self._model.get_user_servers(user_id=self._user.id)
        _, owners = self._model.get_tool_catalogue(user_id=self._user.id)
        rows = [self._row_data(s, owners) for s in servers]
        if self._screen_view is None:
            self._view.show_servers(rows)
            return
        # The screen-control servers are listed under their consent box
        # instead of with the rest.
        self._view.show_servers([row for row in rows if not row['screen_control']])
        self._screen_view.show_servers([row for row in rows if row['screen_control']])
        self._screen_view.set_allowed(self._model.is_screen_control_allowed(self._user.id))

    def _tool_list(self, server: MCPServer, owners: dict) -> list[dict]:
        screen_control = is_screen_control(server)
        tools = []
        for spec in server.known_tools:
            name = spec.get('name')
            if not name:
                continue
            owner = owners.get(name)
            tools.append({
                'name': name,
                'description': (spec.get('description') or '').strip(),
                'asks_by_default': self._approval_policy.requires_approval(
                    name, is_builtin=server.is_builtin),
                'auto_approved': server.allows_without_asking(name),
                # Set for the whole server by the screen-control consent.
                'locked': screen_control,
                # The model only ever reaches the first server offering a
                # name, so this one's setting would change nothing.
                'shadowed_by': owner.name if owner is not None and owner.id != server.id else None,
            })
        return tools

    def _row_data(self, server: MCPServer, owners: dict) -> dict:
        if server.transport == MCPServer.HTTP:
            target = server.url or ""
        else:
            # Built-in servers store no command; the interpreter is picked at
            # launch time.
            target = " ".join(str(part) for part in
                              [server.command or "python", *server.args])

        if server.id in self._checking:
            status = 'checking'
        elif needs_consent(server):
            status = 'needs_consent'
        elif server.is_broken:
            status = 'error'
        elif not server.is_enabled:
            status = 'off'
        elif server.last_status == MCPServer.STATUS_OK:
            status = 'ok'
        else:
            status = 'unchecked'

        return {
            'id': server.id,
            'name': server.name,
            'transport': server.transport,
            'is_builtin': server.is_builtin,
            'is_enabled': server.is_enabled,
            # Switched on and off by the screen-control consent, not here.
            'screen_control': is_screen_control(server),
            'detail': server.description or target,
            'target': target,
            'status': status,
            'tools': len(server.known_tools),
            'tool_list': self._tool_list(server, owners),
            'error_code': server.last_error_code,
            'error': server.last_error,
        }

    def handle_add(self, form: dict):
        try:
            server = parse_server_form(form)
        except ValueError as e:
            self._view.show_form_error(str(e))
            return

        try:
            server_id = self._model.add_user_server(user_id=self._user.id, **server)
        except Exception as e:
            self._view.show_form_error(f"Could not add the server: {e}")
            return
        if server_id is None:
            self._view.show_form_error(
                f'A server named "{server["name"]}" already exists.')
            return

        self._view.close_form()
        # Checked straight away: until a check succeeds the server has no
        # known tools, so the model would not be offered any of them.
        self._start_check(server_id)

    def handle_delete(self, server_id: str):
        server = self._model.get_server(server_id)
        # Built-in servers are seeded again on every login, so deleting one
        # would not stick; the view offers no delete button for them.
        if server is None or server.is_builtin or server_id in self._checking:
            self.refresh()
            return

        self._stop_server(server_id)
        self._model.delete_server(server_id)
        self.refresh()

    def handle_auto_approve_changed(self, server_id: str, tool_name: str, allowed: bool):
        """Takes effect on the tool's next call, in a task already running
        too. A card already waiting in a chat still needs its answer."""
        self._model.set_tool_auto_approved(server_id, tool_name, allowed)
        self.refresh()

    def handle_enabled_changed(self, server_id: str, enabled: bool):
        if server_id in self._checking:
            self.refresh()
            return

        self._model.set_server_enabled(server_id, enabled)
        if not enabled:
            self._stop_server(server_id)
            self.refresh()
            return

        server = self._model.get_server(server_id)
        if server is not None and (server.is_broken or server.last_status is None):
            # Switching on a server that failed (or was never checked) would
            # offer the model stale tools. The check switches it back off if
            # it still fails.
            self._start_check(server_id)
        else:
            self.refresh()

    def handle_screen_control_changed(self, allowed: bool):
        server_ids = self._model.set_screen_control_allowed(self._user.id, allowed)
        if not allowed:
            # Left running, they would keep serving the calls of a task
            # already under way.
            for server_id in server_ids:
                self._stop_server(server_id)
            self.refresh()
            return

        for server_id in server_ids:
            server = self._model.get_server(server_id)
            if server is not None and (server.is_broken or server.last_status is None):
                # Same as switching on any server: until a check succeeds,
                # its cached tools may be stale or missing.
                self._start_check(server_id)
        self.refresh()

    def handle_check(self, server_id: str):
        self._start_check(server_id)

    def check_all(self):
        """Checks every server of this user one after another - run in the
        background on login, so a slow server never holds up the window."""
        servers = self._model.get_user_servers(user_id=self._user.id)
        self._track(asyncio.create_task(self._check_all([s.id for s in servers])))

    def _start_check(self, server_id: str):
        if server_id in self._checking:
            return
        self._checking.add(server_id)
        self.refresh()
        self._track(asyncio.create_task(self._check(server_id)))

    def _track(self, task: asyncio.Task):
        self._check_tasks.add(task)
        task.add_done_callback(self._check_tasks.discard)

    async def _check(self, server_id: str):
        """Runs one check; the caller has already marked it as checking."""
        try:
            await self._model.probe_server(server_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[MCP] Check of {server_id} failed: {e}")
        finally:
            self._checking.discard(server_id)
        self.refresh()

    async def _check_all(self, server_ids: list[str]):
        for server_id in server_ids:
            # Marked only when its turn comes, so the servers still waiting
            # stay usable; one the user is already checking is skipped.
            if server_id in self._checking:
                continue
            self._checking.add(server_id)
            self.refresh()
            await self._check(server_id)
        self._report_broken(len(server_ids))

    def _report_broken(self, checked: int):
        broken = self._model.get_broken_servers(user_id=self._user.id)
        print(f"[MCP] Checked {checked} server(s) for {self._user.username}; "
              f"{len(broken)} unavailable")
        for server in broken:
            detail = (server.last_error or "").splitlines()
            print(f"[MCP]   {server.name} disabled — {server.last_error_code}"
                  f"{': ' + detail[0] if detail else ''}")

    def _stop_server(self, server_id: str):
        task = asyncio.create_task(self._mcp_registry.stop_server(server_id))
        self._stop_tasks.add(task)
        task.add_done_callback(self._stop_tasks.discard)
