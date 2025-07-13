from PyQt6.QtCore import pyqtSignal, QObject
from core.models import User
from interface.gui.view import RegistrationWindow, LoginWindow, MainWindow, NewChatWindow
from core.services import AuthService, ChatService


class ViewManager:

    def __init__(self, main_view: MainWindow, new_chat_view: NewChatWindow, login_view: LoginWindow, registration_view: RegistrationWindow):
        self.login_view = login_view
        self.registration_view = registration_view
        self.main_view = main_view
        self.new_chat_view = new_chat_view

        self.login_view.switch_to_registration.connect(self.show_registration)
        self.registration_view.switch_to_login.connect(self.show_login)
        self.main_view.logout_requested.connect(self.handle_logout)
        self.main_view.new_chat.connect(self.show_new_chat_view)
        self.new_chat_view.on_submit.connect(self.hide_new_chat_view)

    def show_login(self):
        self.main_view.hide()
        self.registration_view.hide()
        self.login_view.show()

    def show_registration(self):
        self.main_view.hide()
        self.login_view.hide()
        self.registration_view.show()

    def show_main_window(self):
        self.login_view.hide()
        self.registration_view.hide()
        self.main_view.show()

    def handle_logout(self):
        self.main_view.hide()
        self.login_view.show()

    def show_new_chat_view(self):
        self.new_chat_view.show()

    def hide_new_chat_view(self):
        self.new_chat_view.hide()


class RegistrationController(QObject):
    def __init__(self, model: AuthService, view: RegistrationWindow):
        super().__init__()
        self._model = model
        self._view = view

        self._view.registration_submitted.connect(self.handle_registration)

    def show(self):
        """
        Displays the registration window.
        """
        self._view.show()

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
    login_successful = pyqtSignal(User)

    def __init__(self, model: AuthService, view: LoginWindow):
        super().__init__()
        self._model = model
        self._view = view

        self._view.login_submitted.connect(self.handle_login)

    def show(self):
        self._view.show()

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
    def __init__(self, user: User, model: ChatService, view: MainWindow):
        super().__init__()
        self._model = model
        self._view = view
        self._user = user

    def show(self):
        self._view.show()

    def update_chat_list_in_view(self):
        chat_objects = self._model.get_all_user_chats(user_id=self._user.id)
        chats_for_view = [{'id': chat.id, 'title': chat.title}
                          for chat in chat_objects]
        self._view.update_chats_list(chats_for_view)

    def handle_create_new_chat(self, chat_data: dict):
        chat_title = chat_data['title']
        if not chat_title:
            print("Chat title cannot be empty.")
            return
        self._model.create_new_chat(
            user_id=self._user.id, chat_title=chat_title)

        self.update_chat_list_in_view()
