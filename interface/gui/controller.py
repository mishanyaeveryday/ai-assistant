from PySide6.QtCore import Signal, QObject
from core.models import User, MCPServer
from interface.gui.view import RegistrationPage, LoginPage, ChatPage, SettingsPage, AppWindow, MCPServersSection
from core.services import AuthService, ChatService, MessageService, AIClientService, MCPServerService
from interface.gui.worker import AIWorker
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

    def disconnect_view(self):
        """A fresh controller is built on every login, so the previous one has
        to let go of the (long-lived) view first - otherwise a second login
        would handle each action twice."""
        self._view.new_chat_requested.disconnect(self.handle_create_new_chat)
        self._view.chat_delete_requested.disconnect(self.handle_delete_chat)

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
    def __init__(self, model: AIClientService, view: ChatPage, mcp_registry):
        super().__init__()
        self._model = model
        self._view = view
        self._mcp_registry = mcp_registry
        self._tool_approval = HumanToolApproval(parent_widget=self._view)
        self._approval_policy = ToolsApprovalPolicy()
        self._view.send_input.connect(self.handle_prompt)

    def handle_prompt(self, chat_id, user_input):
        self._view.set_input_enabled(False)

        self.worker = AIWorker(
            self._model,
            chat_id,
            user_input,
            mcp_registry=self._mcp_registry,
            approve_tool=self._tool_approval.approve,
            tools_approval_policy=self._approval_policy,
        )

        self.worker.finished.connect(self.handle_ai_response)

        self.worker.error.connect(self.handle_ai_error)

        self.worker.finished.connect(self.worker.deleteLater)
        asyncio.create_task(self.worker.run())

    def handle_ai_response(self, response_dict):
        self._view.set_input_enabled(True)

        try:

            if response_dict and 'output' in response_dict:
                assistant_output = response_dict['output']
                self._view.add_assistant_message(assistant_output)
            else:
                self._view.add_assistant_message(
                    "Sorry, I received an invalid response.")
        except Exception as e:
            self.handle_ai_error(f"Error processing response: {e}")

    def handle_ai_error(self, error_message):
        self._view.set_input_enabled(True)

        self._view.add_assistant_message(
            f"Sorry, an error occurred: {error_message}")


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
        for task in list(self._check_tasks):
            task.cancel()

    def refresh(self):
        if not self._active:
            return
        servers = self._model.get_user_servers(user_id=self._user.id)
        self._view.show_servers([self._row_data(s) for s in servers])

    def _row_data(self, server: MCPServer) -> dict:
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
