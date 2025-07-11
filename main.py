import sys
from PyQt6.QtWidgets import QApplication

from db.database import Chat_DB, MessageHistory_DB, User_DB
from core.services import AuthService

from interface.gui.view import RegistrationWindow
from interface.gui.controller import RegistrationController


def start_gui():
    user_db_instance = User_DB()
    user_db_instance.create_table()

    chat_db_instance = Chat_DB()
    chat_db_instance.create_table()

    history_db_instance = MessageHistory_DB()
    history_db_instance.create_table()

    app = QApplication(sys.argv)

    auth_model = AuthService(user_db=user_db_instance)

    registration_view = RegistrationWindow()

    controller = RegistrationController(
        model=auth_model, view=registration_view)

    controller.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    start_gui()
