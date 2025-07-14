import sys
from PyQt6.QtWidgets import QApplication

from db.database import Chat_DB, MessageHistory_DB, User_DB
from core.models import User
from core.services import AuthService, ChatService, MessageService

from interface.gui.view import RegistrationWindow, LoginWindow, MainWindow, NewChatWindow
from interface.gui.controller import RegistrationController, LoginController, MainWindowController, ViewManager, MessageController


def start_gui():
    user_db_instance = User_DB()
    user_db_instance.create_table()

    chat_db_instance = Chat_DB()
    chat_db_instance.create_table()

    message_history_db_instance = MessageHistory_DB()
    message_history_db_instance.create_table()

    app = QApplication(sys.argv)

    auth_model = AuthService(user_db=user_db_instance)
    chat_model = ChatService(chat_db=chat_db_instance)
    message_model = MessageService(message_db=message_history_db_instance)
    # Views
    main_view = MainWindow()
    new_chat_window = NewChatWindow()
    registration_view = RegistrationWindow()
    login_view = LoginWindow()

    view_manager = ViewManager(
        main_view=main_view, new_chat_view=new_chat_window, login_view=login_view, registration_view=registration_view)

    # Controllers
    registration_controller = RegistrationController(
        model=auth_model, view=registration_view)

    login_controller = LoginController(
        model=auth_model, view=login_view)

    message_controller = MessageController(model=message_model, view=main_view)

    main_window_controller = None

    def on_login_success(user: User):

        nonlocal main_window_controller

        main_window_controller = MainWindowController(user=user,
                                                      model=chat_model, view=main_view)
        main_view.set_user_data(
            {"username": user.username, "email": user.email})

        main_window_controller.update_chat_list_in_view()

        new_chat_window.on_submit.connect(
            main_window_controller.handle_create_new_chat)

        view_manager.show_main_window()

    login_controller.login_successful.connect(on_login_success)
    view_manager.show_login()

    sys.exit(app.exec())


if __name__ == '__main__':
    start_gui()
