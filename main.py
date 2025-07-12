import sys
from PyQt6.QtWidgets import QApplication

from db.database import Chat_DB, MessageHistory_DB, User_DB
from core.services import AuthService

from interface.gui.view import RegistrationWindow, LoginWindow, MainWindow
from interface.gui.controller import RegistrationController, LoginController, ViewManager
from core.models import User


def start_gui():
    user_db_instance = User_DB()
    user_db_instance.create_table()

    chat_db_instance = Chat_DB()
    chat_db_instance.create_table()

    history_db_instance = MessageHistory_DB()
    history_db_instance.create_table()

    app = QApplication(sys.argv)

    auth_model = AuthService(user_db=user_db_instance)

    # Views
    main_view = MainWindow()
    registration_view = RegistrationWindow()
    login_view = LoginWindow()

    view_manager = ViewManager(main_view, login_view, registration_view)

    # Controllers
    registration_controller = RegistrationController(
        model=auth_model, view=registration_view)

    login_controller = LoginController(
        model=auth_model, view=login_view)

    def on_login_success(user: User):
        main_view.set_user_data(
            {"username": user.username, "email": user.email})

        view_manager.show_main_window()

    login_controller.login_successful.connect(on_login_success)
    view_manager.show_login()

    sys.exit(app.exec())


if __name__ == '__main__':
    start_gui()
