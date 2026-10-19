from PySide6.QtCore import Signal, QObject
from core.models import User
from interface.gui.view import RegistrationPage, LoginPage, ChatPage, SettingsPage, AppWindow
from core.services import AuthService, ChatService, MessageService, AIClientService
from interface.gui.worker import AIWorker
from interface.gui.mcp_tools_approval import HumanToolApproval
from agent.tools_policy import ToolsApprovalPolicy
import asyncio


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
