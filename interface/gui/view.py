from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QLabel, QLineEdit, QFormLayout, QHBoxLayout, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from db.database import User_DB


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-assistant")
        self.resize(900, 550)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)

        self.welcome_label = QLabel("Welcome!")

        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(
            self.logout_requested.emit)

        layout.addWidget(self.welcome_label)
        layout.addWidget(self.logout_button)

    def set_user_data(self, user_data: dict):
        self.welcome_label.setText(f"Welcome, {user_data['username']}!")


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
