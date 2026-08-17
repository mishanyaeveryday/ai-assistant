from db.database import Chat_DB, MessageHistory_DB, User_DB
from core.models import User
from core.services import AuthService, ChatService, MessageService, AIClientService

from interface.gui.view import RegistrationWindow, LoginWindow, MainWindow, NewChatWindow
from interface.gui.controller import RegistrationController, LoginController, MainWindowController, ViewManager, MessageController, AIClientController

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
from agent.mcp_client import MCPClient

from qasync import QEventLoop, asyncSlot
import asyncio


async def setup_mcp(client, view: MainWindow):
    try:
        await client.connect_to_server('mcp_tools/web_search/server.py')
        await client.connect_to_server('mcp_tools/terminal_command/server.py')
        await client.connect_to_server('mcp_tools/filesystem_command/server.py')
        await client.connect_to_server('mcp_tools/screenshot_command/server.py')
        print("MCP Servers connected successfully")
    except Exception as e:
        print(f"MCP Connection Error: {e}")
        view.set_input_enabled(True)


async def main():
    # 1. Initialize DB
    user_db_instance = User_DB()
    user_db_instance.create_table()
    chat_db_instance = Chat_DB()
    chat_db_instance.create_table()
    message_history_db_instance = MessageHistory_DB()
    message_history_db_instance.create_table()

    # 2. Models initialize
    auth_model = AuthService(user_db=user_db_instance)
    chat_model = ChatService(chat_db=chat_db_instance)
    message_model = MessageService(message_db=message_history_db_instance)
    ai_model = AIClientService(message_db=message_history_db_instance)

    # 3. Create Views
    main_view = MainWindow()
    new_chat_window = NewChatWindow()
    registration_view = RegistrationWindow()
    login_view = LoginWindow()

    view_manager = ViewManager(
        main_view=main_view,
        new_chat_view=new_chat_window,
        login_view=login_view,
        registration_view=registration_view
    )

    # 4. Running MCP
    mcp_client = MCPClient()
    connection_mcp_client = asyncio.create_task(
        setup_mcp(mcp_client, main_view))

    # 5. Controllers
    registration_controller = RegistrationController(
        model=auth_model, view=registration_view)
    login_controller = LoginController(model=auth_model, view=login_view)
    message_controller = MessageController(model=message_model, view=main_view)
    ai_controller = AIClientController(
        model=ai_model, view=main_view, mcp_client=mcp_client)

    main_window_controller = None

    def on_login_success(user: User):
        nonlocal main_window_controller
        main_window_controller = MainWindowController(
            user=user, model=chat_model, view=main_view)
        main_view.set_user_data(
            {"username": user.username, "email": user.email})
        main_window_controller.update_chat_list_in_view()
        new_chat_window.on_submit.connect(
            main_window_controller.handle_create_new_chat)
        view_manager.show_main_window()

    login_controller.login_successful.connect(on_login_success)
    view_manager.show_login()

    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    app = QApplication(sys.argv)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    try:
        loop.create_task(main())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
