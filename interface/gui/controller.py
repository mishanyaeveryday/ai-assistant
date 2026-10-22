from PySide6.QtCore import Signal, QObject
from core.models import User, MCPServer
from interface.gui.view import RegistrationPage, LoginPage, ChatPage, SettingsPage, AppWindow, MCPServersSection
from core.services import AuthService, ChatService, MessageService, AIClientService, MCPServerService
from interface.gui.worker import AIWorker, STOPPED_OUTPUT
from interface.gui.mcp_tools_approval import HumanToolApproval
from agent.tools_policy import ToolsApprovalPolicy
import asyncio
import re
import shlex

# Server names also prefix the names of their secrets, which may not contain
# anything else - and a dot is what separates the parts of those names.
_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")


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


def _parse_pairs(text: str, separator: str, key_re: re.Pattern, what: str) -> dict:
    """Reads one `key<separator>value` pair per line. Blank lines and lines
    starting with # are skipped, so a pasted snippet can keep its comments."""
    pairs = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, found, value = line.partition(separator)
        key = key.strip()
        if not found or not key_re.match(key):
            raise ValueError(
                f'{what}: "{line}" is not a valid "name{separator}value" line.')
        if key in pairs:
            raise ValueError(f'{what}: "{key}" is set twice.')
        pairs[key] = value.strip()
    return pairs


def parse_server_form(form: dict) -> dict:
    """Turns what was typed into the add-server form into the arguments of
    MCPServerService.add_user_server. Raises ValueError with a message meant
    for the user."""
    name = form.get('name', '').strip()
    if not name:
        raise ValueError("Name is required.")
    if not _SERVER_NAME_RE.match(name):
        raise ValueError("Name may only contain letters, digits, _ and -.")

    server = {
        'name': name,
        'transport': form.get('transport'),
        'description': form.get('description', '').strip() or None,
    }

    if server['transport'] == MCPServer.STDIO:
        try:
            parts = shlex.split(form.get('command', ''))
        except ValueError as e:
            raise ValueError(f"Command: {e}.") from None
        if not parts:
            raise ValueError("Command is required.")
        server['command'] = parts[0]
        server['args'] = parts[1:]
        server['env'] = _parse_pairs(
            form.get('env', ''), '=', _ENV_KEY_RE, "Environment")
    elif server['transport'] == MCPServer.HTTP:
        url = form.get('url', '').strip()
        if not url.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://.")
        server['url'] = url
        server['headers'] = _parse_pairs(
            form.get('headers', ''), ':', _HEADER_NAME_RE, "Headers")
    else:
        raise ValueError("Choose the server type.")

    return server


class MCPServersController(QObject):
    """Drives the MCP servers section of settings. Built on every login, like
    MainWindowController, since everything it shows belongs to one user - and
    it also runs the connection checks, so the section can show which servers
    are being checked right now."""

    def __init__(self, user: User, model: MCPServerService, view: MCPServersSection, mcp_registry):
        super().__init__()
        self._user = user
        self._model = model
        self._view = view
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
        for task in list(self._check_tasks):
            task.cancel()

    def refresh(self):
        if not self._active:
            return
        servers = self._model.get_user_servers(user_id=self._user.id)
        _, owners = self._model.get_tool_catalogue(user_id=self._user.id)
        self._view.show_servers([self._row_data(s, owners) for s in servers])

    def _tool_list(self, server: MCPServer, owners: dict) -> list[dict]:
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
                'auto_approved': name in server.auto_approved_tools,
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
