import sys
from PyQt6.QtWidgets import QApplication
from core.models import User
from agent.ai_client import AIClient
from interface.gui.view import RegistrationWindow
from core.services import AuthService


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
