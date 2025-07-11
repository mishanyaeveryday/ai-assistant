import sys
from PyQt6.QtWidgets import QApplication
from core.models import User
from agent.ai_client import AIClient
from interface.gui.view import RegistrationWindow, LoginWindow
from core.services import AuthService


class ViewManager:

    def __init__(self, login_view: LoginWindow, registration_view: RegistrationWindow):
        self.login_view = login_view
        self.registration_view = registration_view

        self.login_view.switch_to_registration.connect(self.show_registration)
        self.registration_view.switch_to_login.connect(self.show_login)

    def show_login(self):
        self.registration_view.hide()
        self.login_view.show()

    def show_registration(self):
        self.login_view.hide()
        self.registration_view.show()


class RegistrationController:
    def __init__(self, model: AuthService, view: RegistrationWindow):
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


class LoginController:
    def __init__(self, model: AuthService, view: LoginWindow):
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
            self._view.show_message('Login successful!', is_error=False)

        else:
            self._view.show_message(result, is_error=True)
