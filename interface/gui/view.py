from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QLabel, QLineEdit, QFormLayout, QHBoxLayout, QFrame, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()
    chat_selected = pyqtSignal(str)
    new_chat = pyqtSignal()
    send_input = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-assistant")
        self.resize(900, 550)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QHBoxLayout(self.central_widget)

        left_panel = QFrame()
        left_panel.setFixedWidth(250)
        left_panel.setStyleSheet("background-color: #f0f0f0;")
        left_panel_layout = QVBoxLayout(left_panel)

        self.welcome_label = QLabel("Welcome!")
        self.new_chat_button = QPushButton("+ New Chat")
        self.new_chat_button.clicked.connect(self.new_chat.emit)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self.logout_requested.emit)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.chats_container = QWidget()
        self.chats_layout = QVBoxLayout(
            self.chats_container)
        self.chats_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(self.chats_container)

        left_panel_layout.addWidget(self.welcome_label)
        left_panel_layout.addWidget(self.new_chat_button)
        left_panel_layout.addWidget(QLabel("Your Chats:"))
        left_panel_layout.addWidget(scroll_area)
        left_panel_layout.addStretch()
        left_panel_layout.addWidget(self.logout_button)

        right_panel = QFrame()
        self.right_panel_layout = QVBoxLayout(right_panel)
        self.chat_info = QLabel("Select a chat to start or create a new one.")
        self.chat_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_panel_layout.addWidget(self.chat_info)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        self.chat_buttons = {}
        self.message_layout = None
        self.chat_scroll_area = None
        self.current_chat_id = None

    def set_user_data(self, user_data: dict):
        self.welcome_label.setText(f"Welcome, {user_data['username']}!")

    def show_chat(self, chat_id: str, message_data: dict):
        self.current_chat_id = chat_id
        for i in reversed(range(self.right_panel_layout.count())):
            item = self.right_panel_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        chat_container = QWidget()
        self.messages_layout = QVBoxLayout(chat_container)
        self.messages_layout.setContentsMargins(5, 5, 5, 5)
        self.messages_layout.setSpacing(10)
        self.messages_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop)
        for m in message_data:
            user_message = QLabel(f"<b>You:</b><br>{m['input']}")
            user_message.setWordWrap(True)
            user_message.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            user_message.setStyleSheet(
                "background-color: #e1f5fe; border-radius: 5px; padding: 5px;")
            user_message.setAlignment(Qt.AlignmentFlag.AlignLeft)

            assistant_message = QLabel(f"<b>Assistant:</b><br>{m['output']}")
            assistant_message.setWordWrap(True)
            assistant_message.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            assistant_message.setStyleSheet(
                "background-color: #f1f8e9; border-radius: 5px; padding: 5px;")
            assistant_message.setAlignment(Qt.AlignmentFlag.AlignLeft)

            self.messages_layout.addWidget(user_message)
            self.messages_layout.addWidget(assistant_message)

        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(chat_container)
        self.chat_scroll_area.setStyleSheet("border: none;")

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Start typing a prompt")
        self.send_button = QPushButton("Run")

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.message_input)
        bottom_layout.addWidget(self.send_button)

        self.send_button.clicked.connect(self.send_prompt)
        self.message_input.returnPressed.connect(self.send_prompt)

        self.right_panel_layout.addWidget(self.chat_scroll_area)
        self.right_panel_layout.addLayout(bottom_layout)

        self.scroll_to_bottom()

    def set_input_enabled(self, enabled: bool):
        self.send_button.setEnabled(enabled)
        self.message_input.setEnabled(enabled)

    def send_prompt(self):
        prompt_text = self.message_input.text().strip()

        if prompt_text and self.current_chat_id:
            user_message = QLabel(f"<b>You:</b><br>{prompt_text}")
            user_message.setWordWrap(True)
            user_message.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            user_message.setStyleSheet(
                "background-color: #e1f5fe; border-radius: 5px; padding: 5px;")
            user_message.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.messages_layout.addWidget(user_message)
            self.scroll_to_bottom()

            self.send_input.emit(self.current_chat_id, prompt_text)

            self.message_input.clear()

    def add_assistant_message(self, text: str):
        if self.messages_layout is not None:
            assistant_message = QLabel(f"<b>Assistant:</b><br>{text}")
            assistant_message.setWordWrap(True)
            assistant_message.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            assistant_message.setStyleSheet(
                "background-color: #f1f8e9; border-radius: 5px; padding: 5px;")
            assistant_message.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.messages_layout.addWidget(assistant_message)
            self.scroll_to_bottom()

    def update_chats_list(self, chats_data: list[dict]):
        while self.chats_layout.count():
            item = self.chats_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.chat_buttons.clear()

        if not chats_data:
            no_chats_label = QLabel("No chats yet.")
            self.chats_layout.addWidget(no_chats_label)
            return

        for chat in chats_data:
            chat_id = chat['id']
            chat_title = chat.get('title', f'Chat {chat_id}')

            button = QPushButton(chat_title)

            button.clicked.connect(
                lambda _, cid=chat_id: self.chat_selected.emit(cid))

            self.chats_layout.addWidget(button)
            self.chat_buttons[chat_id] = button

    def scroll_to_bottom(self):
        if self.chat_scroll_area:
            self.chat_scroll_area.verticalScrollBar().setValue(
                self.chat_scroll_area.verticalScrollBar().maximum())


class NewChatWindow(QMainWindow):
    on_submit = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Create new chat")
        self.setFixedSize(400, 200)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        outer_layout = QVBoxLayout(self.central_widget)
        outer_layout.addStretch(1)
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #cccccc;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        self.frame.setMaximumWidth(400)

        frame_layout = QVBoxLayout(self.frame)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Enter title")

        form_layout = QFormLayout()

        form_layout.addRow("Title:", self.title_input)

        self.submit_button = QPushButton("Apply")
        self.submit_button.setMaximumSize(150, 40)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.submit_button)

        frame_layout.addLayout(form_layout)
        frame_layout.addLayout(button_layout)

        frame_container = QHBoxLayout()
        frame_container.addStretch(1)
        frame_container.addWidget(self.frame)
        frame_container.addStretch(1)

        outer_layout.addLayout(frame_container)
        outer_layout.addStretch(1)

        self.submit_button.clicked.connect(self.apply)

    def apply(self):
        chat_data = {
            "title": self.title_input.text(),
        }
        self.on_submit.emit(chat_data)
        self.title_input.clear()


class RegistrationWindow(QMainWindow):

    registration_submitted = pyqtSignal(dict)
    switch_to_login = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-assistant")
        self.resize(900, 550)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        outer_layout = QVBoxLayout(self.central_widget)
        outer_layout.addStretch(1)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #cccccc;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        self.frame.setMaximumWidth(400)

        frame_layout = QVBoxLayout(self.frame)

        form_layout = QFormLayout()

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("example@mail.com")

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("At least 8 characters")

        form_layout.addRow("Username:", self.username_input)
        form_layout.addRow("Email:", self.email_input)
        form_layout.addRow("Password:", self.password_input)

        self.register_button = QPushButton("Sign up")
        self.register_button.setMaximumSize(150, 40)

        self.login_button = QPushButton("Back to sign in")
        self.login_button.setMaximumSize(150, 40)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.register_button)
        button_layout.addWidget(self.login_button)
        button_layout.addStretch(1)

        self.main_title = QLabel("AI-assistant")
        self.main_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.main_title)
        frame_layout.addLayout(form_layout)
        frame_layout.addLayout(button_layout)
        frame_layout.addWidget(self.message_label)

        frame_container = QHBoxLayout()
        frame_container.addStretch(1)
        frame_container.addWidget(self.frame)
        frame_container.addStretch(1)

        outer_layout.addLayout(frame_container)
        outer_layout.addStretch(1)

        self.register_button.clicked.connect(self.on_submit)
        self.login_button.clicked.connect(self.on_login)

    def on_submit(self):
        user_data = {
            "username": self.username_input.text(),
            "email": self.email_input.text(),
            "password": self.password_input.text()
        }
        self.registration_submitted.emit(user_data)

    def on_login(self):
        self.switch_to_login.emit()

    def show_message(self, text: str, is_error: bool = False):
        self.message_label.setText(text)
        color = "red" if is_error else "green"
        self.message_label.setStyleSheet(f"color: {color};")

    def clear_form(self):
        self.username_input.clear()
        self.email_input.clear()
        self.password_input.clear()


class LoginWindow(QMainWindow):
    login_submitted = pyqtSignal(dict)
    switch_to_registration = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-assistant")
        self.resize(900, 550)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        outer_layout = QVBoxLayout(self.central_widget)
        outer_layout.addStretch(1)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #cccccc;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        self.frame.setMaximumWidth(400)

        frame_layout = QVBoxLayout(self.frame)

        form_layout = QFormLayout()

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("At least 8 characters")

        form_layout.addRow("Username:", self.username_input)
        form_layout.addRow("Password:", self.password_input)

        self.login_button = QPushButton("Sign in")
        self.login_button.setMaximumSize(150, 40)

        self.register_button = QPushButton("Create a new account")
        self.register_button.setMaximumSize(150, 40)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.register_button)
        button_layout.addStretch(1)

        self.main_title = QLabel("AI-assistant")
        self.main_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.main_title)
        frame_layout.addLayout(form_layout)
        frame_layout.addLayout(button_layout)
        frame_layout.addWidget(self.message_label)

        frame_container = QHBoxLayout()
        frame_container.addStretch(1)
        frame_container.addWidget(self.frame)
        frame_container.addStretch(1)

        outer_layout.addLayout(frame_container)
        outer_layout.addStretch(1)

        self.login_button.clicked.connect(self.on_submit)
        self.register_button.clicked.connect(self.on_registrate)

    def on_submit(self):
        user_data = {
            "username": self.username_input.text(),
            "password": self.password_input.text()
        }
        self.login_submitted.emit(user_data)

    def on_registrate(self):
        self.switch_to_registration.emit()

    def show_message(self, text: str, is_error: bool = False):
        self.message_label.setText(text)
        color = "red" if is_error else "green"
        self.message_label.setStyleSheet(f"color: {color};")

    def clear_form(self):
        self.username_input.clear()
        self.email_input.clear()
        self.password_input.clear()
