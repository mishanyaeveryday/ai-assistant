from db.database import Chat_DB, MessageHistory_DB, User_DB, MCPServer_DB, Secret_DB
from core.models import User
from core.services import AuthService, ChatService, MessageService, AIClientService, MCPServerService, SecretService
from agent.mcp_registry import MCPRegistry

from interface.gui.view import RegistrationPage, LoginPage, ChatPage, SettingsPage, AppWindow, MCPServersSection
from interface.gui.controller import RegistrationController, LoginController, MainWindowController, ViewManager, MessageController, AIClientController, MCPServersController

import sys
import os
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
from agent.mcp_client import MCPClient, IDLE_SWEEP_SECONDS

from qasync import QEventLoop, asyncSlot
import asyncio


async def sweep_idle_mcp_servers(client: MCPClient):
    """Shuts down connections nothing has used for a while.

    Counted from the last call through each connection rather than from any
    notion of a session ending - the app can be closed without warning, and a
    server left running would outlive it."""
    while True:
        await asyncio.sleep(IDLE_SWEEP_SECONDS)
        try:
            await client.close_idle()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[MCP] Idle sweep error: {e}")


async def main():
    # 1. Initialize DB
    user_db_instance = User_DB()
    user_db_instance.create_table()
    chat_db_instance = Chat_DB()
    chat_db_instance.create_table()
    message_history_db_instance = MessageHistory_DB()
    message_history_db_instance.create_table()
    mcp_server_db_instance = MCPServer_DB()
    mcp_server_db_instance.create_table()
    secret_db_instance = Secret_DB()
    secret_db_instance.create_table()

    # 2. Models initialize
    auth_model = AuthService(user_db=user_db_instance)
    chat_model = ChatService(chat_db=chat_db_instance)
    message_model = MessageService(message_db=message_history_db_instance)
    ai_model = AIClientService(message_db=message_history_db_instance)
    secret_model = SecretService(secret_db=secret_db_instance)
    mcp_server_model = MCPServerService(
        mcp_server_db=mcp_server_db_instance, secret_service=secret_model)

    # 3. Create Views
    app_window = AppWindow()
    main_view = ChatPage()
    registration_view = RegistrationPage()
    login_view = LoginPage()
    settings_view = SettingsPage()
    mcp_servers_view = MCPServersSection()
    settings_view.add_section(mcp_servers_view)

    view_manager = ViewManager(
        app_window=app_window,
        main_view=main_view,
        login_view=login_view,
        registration_view=registration_view,
        settings_view=settings_view
    )

    # 4. MCP runtime - nothing is started here. A server comes up the first
    # time the model calls one of its tools, and goes down again once it has
    # been idle for a while.
    mcp_client = MCPClient()
    mcp_registry = MCPRegistry(mcp_server_model, mcp_client)
    idle_sweep_task = asyncio.create_task(sweep_idle_mcp_servers(mcp_client))

    # 5. Controllers
    registration_controller = RegistrationController(
        model=auth_model, view=registration_view)
    login_controller = LoginController(model=auth_model, view=login_view)
    message_controller = MessageController(model=message_model, view=main_view)
    ai_controller = AIClientController(
        model=ai_model, view=main_view, mcp_registry=mcp_registry)

    main_window_controller = None
    mcp_servers_controller = None

    def on_login_success(user: User):
        nonlocal main_window_controller, mcp_servers_controller
        if main_window_controller is not None:
            main_window_controller.disconnect_view()
        # Also cancels checks still running from a previous login - they are
        # for the wrong user.
        if mcp_servers_controller is not None:
            mcp_servers_controller.disconnect_view()

        # Backfills the built-in servers for this user; a no-op once they are
        # already recorded.
        mcp_server_model.ensure_builtin_servers(user_id=user.id)
        # Point the runtime at this user's servers; a second login must not
        # inherit the previous user's catalogue.
        mcp_registry.set_user(user.id)

        main_window_controller = MainWindowController(
            user=user, model=chat_model, view=main_view)
        user_data = {"username": user.username, "email": user.email}
        main_view.set_user_data(user_data)
        settings_view.set_user_data(user_data)
        main_window_controller.update_chat_list_in_view()
        mcp_servers_controller = MCPServersController(
            user=user, model=mcp_server_model, view=mcp_servers_view,
            mcp_registry=mcp_registry)
        view_manager.show_main_window()

        # Kicked off after the window is up so a slow or hanging server never
        # holds up the login.
        mcp_servers_controller.check_all()

    login_controller.login_successful.connect(on_login_success)
    view_manager.show_login()
    app_window.show()

    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    app = QApplication(sys.argv)

    style_path = os.path.join(os.path.dirname(
        __file__), "interface", "gui", "style.qss")
    with open(style_path, encoding="utf-8") as f:
        app.setStyleSheet(f.read())

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    try:
        loop.create_task(main())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
