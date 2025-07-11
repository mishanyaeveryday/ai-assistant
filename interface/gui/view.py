from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QLineEdit, QFormLayout
from PyQt6.QtCore import pyqtSignal


class RegistrationWindow(QMainWindow):

    registration_submitted = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Registration")
        self.setFixedSize(400, 250)

        self.central_widget = QWidget()
        self.main_layout = QVBoxLayout(self.central_widget)

        form_layout = QFormLayout()

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("example@mail.com")

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Не менее 8 символов")

        form_layout.addRow("Username:", self.username_input)
        form_layout.addRow("Email:", self.email_input)
        form_layout.addRow("Password:", self.password_input)

        self.register_button = QPushButton("Registrate")
        self.message_label = QLabel("")

        self.main_layout.addLayout(form_layout)
        self.main_layout.addWidget(self.register_button)
        self.main_layout.addWidget(self.message_label)

        self.setCentralWidget(self.central_widget)

        self.register_button.clicked.connect(self.on_submit)

    def on_submit(self):

        user_data = {
            "username": self.username_input.text(),
            "email": self.email_input.text(),
            "password": self.password_input.text()
        }
        self.registration_submitted.emit(user_data)

    def show_message(self, text: str, is_error: bool = False):
        self.message_label.setText(text)
        color = "red" if is_error else "green"
        self.message_label.setStyleSheet(f"color: {color};")

    def clear_form(self):
        self.username_input.clear()
        self.email_input.clear()
        self.password_input.clear()
