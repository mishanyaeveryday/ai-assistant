import sys
from PyQt6.QtWidgets import QApplication

from db.database import Chat_DB, MessageHistory_DB, User_DB
from core.services import AuthService

from interface.gui.view import RegistrationWindow, LoginWindow
from interface.gui.controller import RegistrationController, LoginController, ViewManager


def start_gui():
    user_db_instance = User_DB()
    user_db_instance.create_table()

    chat_db_instance = Chat_DB()
    chat_db_instance.create_table()

    history_db_instance = MessageHistory_DB()
    history_db_instance.create_table()

    app = QApplication(sys.argv)

    # Модель (остается как есть)
    # Использую заглушку AuthService
    auth_model = AuthService(user_db=user_db_instance)

    # Представления (Views)
    registration_view = RegistrationWindow()
    login_view = LoginWindow()

    # --- Создаем наш менеджер окон ---
    view_manager = ViewManager(login_view, registration_view)

    # Контроллеры (остаются как есть, они работают со своими моделями и представлениями)
    registration_controller = RegistrationController(
        model=auth_model, view=registration_view)

    login_controller = LoginController(
        model=auth_model, view=login_view)

    # --- Показываем начальное окно через менеджер ---
    view_manager.show_login()

    sys.exit(app.exec())


if __name__ == '__main__':
    start_gui()
