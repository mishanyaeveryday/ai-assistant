import asyncio
import json
import re
from pathlib import Path

import shiboken6
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                               QPushButton, QLabel, QLineEdit, QFormLayout, QHBoxLayout, QFrame, QScrollArea,
                               QButtonGroup, QGraphicsDropShadowEffect, QPlainTextEdit, QStackedWidget,
                               QMessageBox, QInputDialog, QDialog)
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtCore import Qt, Signal

_IMAGE_MARKER_RE = re.compile(r"\[GENERATED_IMAGE:(.+?)\]")
_MAX_IMAGE_WIDTH = 420
_CHAT_TITLE_FIELD_WIDTH = 280
_IMAGE_PLACEHOLDER_STYLE = (
    "color: #8a8f98; font-style: italic; background-color: #f1f8e9; "
    "border-radius: 5px; padding: 5px;"
)


def _split_text_and_images(raw_text) -> tuple[str, list[str]]:
    raw_text = raw_text or ""
    image_paths = [m.strip()
                   for m in _IMAGE_MARKER_RE.findall(raw_text) if m.strip()]
    clean_text = _IMAGE_MARKER_RE.sub("", raw_text).strip()
    return clean_text, image_paths


async def _load_image_into_label(path: str, label: QLabel) -> None:
    """Read and decode the image off the GUI thread, then drop it into
    `label` — unless the chat was switched away in the meantime and `label`
    has already been torn down, in which case this just quietly does nothing."""
    try:
        data = await asyncio.to_thread(Path(path).read_bytes)
    except OSError:
        data = None

    if not shiboken6.isValid(label):
        return

    pixmap = QPixmap()
    if data is None or not pixmap.loadFromData(data):
        label.setText("(image unavailable)")
        label.setStyleSheet(_IMAGE_PLACEHOLDER_STYLE)
        return

    if pixmap.width() > _MAX_IMAGE_WIDTH:
        pixmap = pixmap.scaledToWidth(
            _MAX_IMAGE_WIDTH, Qt.TransformationMode.SmoothTransformation)
    label.setPixmap(pixmap)
    label.setStyleSheet("")


def build_assistant_bubble(text: str) -> QWidget:
    clean_text, image_paths = _split_text_and_images(text)

    bubble = QWidget()
    layout = QVBoxLayout(bubble)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    if clean_text:
        label = QLabel(f"<b>Assistant:</b><br>{clean_text}")
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(
            "background-color: #f1f8e9; border-radius: 5px; padding: 5px;")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(label)

    for path in image_paths:
        # Text renders immediately; each image loads on its own afterwards so a
        # slow/large chart never blocks opening the chat, and switching chats
        # again mid-load can't crash into an already-destroyed widget.
        image_label = QLabel("Loading image…")
        image_label.setStyleSheet(_IMAGE_PLACEHOLDER_STYLE)
        image_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(image_label)
        asyncio.ensure_future(_load_image_into_label(path, image_label))

    return bubble


class ApprovalBubble(QWidget):
    """Inline chat cell asking the user to allow/deny a sensitive tool call,
    used instead of a blocking popup dialog."""

    decided = Signal(bool)

    _MIN_DETAILS_LINES = 1
    _MAX_DETAILS_LINES = 8
    _LINE_HEIGHT_PX = 17
    _DETAILS_PADDING_PX = 16

    def __init__(self, tool_name: str, args: dict, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(
            "background-color: #fff8e1; border: 1px solid #f0d98c; border-radius: 8px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        title = QLabel(f"<b>Approval needed:</b> run <code>{tool_name}</code>")
        title.setWordWrap(True)
        card_layout.addWidget(title)

        details_text = self._format_args(args)
        details = QPlainTextEdit(details_text)
        details.setReadOnly(True)
        details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        details.setFixedHeight(self._details_height(details_text))
        details.setStyleSheet(
            "font-family: Menlo, Consolas, monospace; font-size: 12px; "
            "background-color: #fffdf5; border: 1px solid #e7d9a0; border-radius: 4px; padding: 4px;")
        card_layout.addWidget(details)

        self._status_label = QLabel("")
        self._status_label.hide()
        card_layout.addWidget(self._status_label)

        self._button_row = QHBoxLayout()
        self._deny_button = QPushButton("Deny")
        self._approve_button = QPushButton("Approve")
        self._deny_button.setStyleSheet(
            "background-color: #e53935;")
        self._approve_button.setStyleSheet(
            "background-color: #43a047;")
        self._button_row.addStretch(1)
        self._button_row.addWidget(self._deny_button)
        self._button_row.addWidget(self._approve_button)
        card_layout.addLayout(self._button_row)

        self._approve_button.clicked.connect(lambda: self._resolve(True))
        self._deny_button.clicked.connect(lambda: self._resolve(False))

        outer.addWidget(card)

    @classmethod
    def _details_height(cls, text: str) -> int:
        line_count = text.count("\n") + 1
        clamped = min(max(line_count, cls._MIN_DETAILS_LINES),
                      cls._MAX_DETAILS_LINES)
        return clamped * cls._LINE_HEIGHT_PX + cls._DETAILS_PADDING_PX

    @staticmethod
    def _format_args(args: dict) -> str:
        if not args:
            return "(no arguments)"
        try:
            return json.dumps(args, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(args)

    def _resolve(self, approved: bool):
        self._approve_button.setEnabled(False)
        self._deny_button.setEnabled(False)
        self._approve_button.hide()
        self._deny_button.hide()
        self._status_label.setStyleSheet(
            f"font-weight: 600; color: {'#2e7d32' if approved else '#c62828'};")
        self._status_label.setText("Approved" if approved else "Denied")
        self._status_label.show()
        self.decided.emit(approved)


def apply_card_shadow(widget):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(24)
    shadow.setXOffset(0)
    shadow.setYOffset(4)
    shadow.setColor(QColor(0, 0, 0, 40))
    widget.setGraphicsEffect(shadow)


class AppWindow(QMainWindow):
    """The single top-level window for the app. It never closes/reopens -
    logging in, registering, and chatting are all pages swapped in and out
    of the same QStackedWidget, so the window itself keeps its position,
    size, and identity throughout."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-assistant")
        self.resize(900, 550)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

    def add_page(self, page: QWidget) -> None:
        self.stack.addWidget(page)

    def show_page(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(page)


class SettingsPage(QWidget):
    """Settings is a page of the one window, like login and chat - not a
    separate window."""

    close_requested = Signal()

    def __init__(self):
        super().__init__()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(24, 20, 24, 20)
        outer_layout.setSpacing(16)

        header = QHBoxLayout()
        self.back_button = QPushButton("← Back")
        self.back_button.setObjectName("back_button")
        self.back_button.setMaximumWidth(110)
        self.back_button.clicked.connect(self.close_requested.emit)

        title = QLabel("Settings")
        title.setObjectName("app_title")

        header.addWidget(self.back_button)
        header.addSpacing(8)
        header.addWidget(title)
        header.addStretch(1)
        outer_layout.addLayout(header)

        # Sections live inside a scroll area so this keeps working as more of
        # them arrive.
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        sections = QWidget()
        self.sections_layout = QVBoxLayout(sections)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(16)
        self.sections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(sections)
        outer_layout.addWidget(scroll_area, 1)

        account_card = QFrame()
        account_card.setObjectName("card")
        account_layout = QFormLayout(account_card)
        account_heading = QLabel("Account")
        account_heading.setObjectName("section_label")
        self.username_value = QLabel("-")
        self.email_value = QLabel("-")
        account_layout.addRow(account_heading)
        account_layout.addRow("Username:", self.username_value)
        account_layout.addRow("Email:", self.email_value)
        self.sections_layout.addWidget(account_card)

    def add_section(self, widget: QWidget) -> None:
        """Hook for the sections still to come (MCP servers, secrets)."""
        self.sections_layout.addWidget(widget)

    def set_user_data(self, user_data: dict):
        self.username_value.setText(user_data.get('username', '-'))
        self.email_value.setText(user_data.get('email', '-'))


class ChatPage(QWidget):
    logout_requested = Signal()
    chat_selected = Signal(str)
    chat_delete_requested = Signal(str)
    new_chat_requested = Signal(str)
    settings_requested = Signal()
    send_input = Signal(str, str)

    def __init__(self):
        super().__init__()

        main_layout = QHBoxLayout(self)

        left_panel = QFrame()
        left_panel.setObjectName("left_panel")
        left_panel.setFixedWidth(250)
        left_panel_layout = QVBoxLayout(left_panel)
        left_panel_layout.setContentsMargins(12, 16, 12, 16)
        left_panel_layout.setSpacing(8)

        self.welcome_label = QLabel("Welcome!")
        self.welcome_label.setObjectName("app_title")
        self.new_chat_button = QPushButton("+ New Chat")
        self.new_chat_button.clicked.connect(self.prompt_new_chat)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        # U+FE0E asks for the outline glyph; without it macOS renders the gear
        # as a full-colour emoji, which looks out of place next to Logout.
        self.settings_button = QPushButton("⚙︎")
        self.settings_button.setObjectName("settings_button")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setFixedSize(36, 36)
        self.settings_button.clicked.connect(self.settings_requested.emit)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.chats_container = QWidget()
        self.chats_layout = QVBoxLayout(
            self.chats_container)
        self.chats_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(self.chats_container)

        chats_label = QLabel("Your Chats")
        chats_label.setObjectName("section_label")

        left_panel_layout.addWidget(self.welcome_label)
        left_panel_layout.addWidget(self.new_chat_button)
        left_panel_layout.addWidget(chats_label)
        left_panel_layout.addWidget(scroll_area)
        left_panel_layout.addStretch()

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addWidget(self.logout_button, 1)
        bottom_row.addWidget(self.settings_button)
        left_panel_layout.addLayout(bottom_row)

        right_panel = QFrame()
        self.right_panel_layout = QVBoxLayout(right_panel)
        self.chat_info = QLabel("Select a chat to start or create a new one.")
        self.chat_info.setObjectName("placeholder_text")
        self.chat_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_panel_layout.addWidget(self.chat_info)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        self.chat_buttons = {}
        self.chats_button_group = None
        self.messages_layout = None
        self.chat_scroll_area = None
        self.message_input = None
        self.send_button = None
        self.current_chat_id = None

    def set_user_data(self, user_data: dict):
        self.welcome_label.setText(f"Welcome, {user_data['username']}!")

    def _clear_right_panel(self):
        """Tears down whatever the right panel is showing and drops every
        reference to it. The widgets are gone on the C++ side after this, so
        the attributes must not keep pointing at them."""
        for i in reversed(range(self.right_panel_layout.count())):
            item = self.right_panel_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        self.messages_layout = None
        self.chat_scroll_area = None
        self.message_input = None
        self.send_button = None

    def clear_chat_view(self):
        """Returns the right panel to its "nothing selected" state, used when
        the chat that was open gets deleted."""
        self._clear_right_panel()
        self.current_chat_id = None

        self.chat_info = QLabel("Select a chat to start or create a new one.")
        self.chat_info.setObjectName("placeholder_text")
        self.chat_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_panel_layout.addWidget(self.chat_info)

    def show_chat(self, chat_id: str, message_data: dict):
        self._clear_right_panel()
        self.current_chat_id = chat_id

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

            assistant_bubble = build_assistant_bubble(m['output'])

            self.messages_layout.addWidget(user_message)
            self.messages_layout.addWidget(assistant_bubble)

        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(chat_container)
        self.chat_scroll_area.setStyleSheet("border: none;")

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Start typing a prompt")
        self.send_button = QPushButton("Run")

        # The input row lives in its own widget rather than a bare sub-layout:
        # the panel is torn down widget by widget, and a plain layout would be
        # skipped there, leaving the old input box painted over the panel.
        bottom_row = QWidget()
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self.message_input)
        bottom_layout.addWidget(self.send_button)

        self.send_button.clicked.connect(self.send_prompt)
        self.message_input.returnPressed.connect(self.send_prompt)

        self.right_panel_layout.addWidget(self.chat_scroll_area)
        self.right_panel_layout.addWidget(bottom_row)

        self.scroll_to_bottom()

    def set_input_enabled(self, enabled: bool):
        # The chat can be closed (deleted) while a request is still in flight,
        # in which case these widgets no longer exist.
        if self.send_button is None or not shiboken6.isValid(self.send_button):
            return
        self.send_button.setEnabled(enabled)
        self.message_input.setEnabled(enabled)

    def send_prompt(self):
        if self.message_input is None:
            return
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
            assistant_bubble = build_assistant_bubble(text)
            self.messages_layout.addWidget(assistant_bubble)
            self.scroll_to_bottom()

    def add_approval_request(self, tool_name: str, args: dict) -> ApprovalBubble:
        bubble = ApprovalBubble(tool_name, args)
        if self.messages_layout is not None:
            self.messages_layout.addWidget(bubble)
            self.scroll_to_bottom()
        return bubble

    def update_chats_list(self, chats_data: list[dict]):
        while self.chats_layout.count():
            item = self.chats_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.chat_buttons.clear()
        self.chats_button_group = QButtonGroup(self)
        self.chats_button_group.setExclusive(True)

        if not chats_data:
            no_chats_label = QLabel("No chats yet.")
            no_chats_label.setObjectName("placeholder_text")
            self.chats_layout.addWidget(no_chats_label)
            return

        for chat in chats_data:
            chat_id = chat['id']
            chat_title = chat.get('title', f'Chat {chat_id}')

            row = QWidget()
            row.setObjectName("chat_row")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            button = QPushButton(chat_title)
            button.setObjectName("chat_button")
            button.setCheckable(True)
            self.chats_button_group.addButton(button)

            button.clicked.connect(
                lambda _, cid=chat_id: self.chat_selected.emit(cid))

            delete_button = QPushButton("✕")
            delete_button.setObjectName("chat_delete_button")
            delete_button.setToolTip(f'Delete "{chat_title}"')
            delete_button.setFixedSize(24, 24)
            delete_button.clicked.connect(
                lambda _, cid=chat_id, title=chat_title: self.confirm_delete_chat(cid, title))

            row_layout.addWidget(button, 1)
            row_layout.addWidget(delete_button)

            self.chats_layout.addWidget(row)
            self.chat_buttons[chat_id] = button

        # The button group is rebuilt from scratch, so the chat that is open
        # on the right has to be re-marked as the selected one.
        open_button = self.chat_buttons.get(self.current_chat_id)
        if open_button is not None:
            open_button.setChecked(True)

    def prompt_new_chat(self):
        """Asks for the new chat's title in a modal dialog, the same kind the
        delete confirmation uses. An empty title is rejected and the dialog
        reopens rather than closing on a chat that was never created."""
        title = ""
        while True:
            title, accepted = self._ask_chat_title(title)
            if not accepted:
                return

            title = title.strip()
            if title:
                self.new_chat_requested.emit(title)
                return

            QMessageBox.warning(self, "New chat", "Title cannot be empty.")

    def _ask_chat_title(self, prefill: str) -> tuple[str, bool]:
        """Builds the dialog by hand instead of using QInputDialog.getText:
        the convenience helper sizes the text field to the label, which comes
        out too cramped for a chat title. Widening the field is what widens
        the dialog - QInputDialog ignores resize() on itself."""
        dialog = QInputDialog(self)
        dialog.setWindowTitle("New chat")
        dialog.setLabelText("Chat title:")
        dialog.setTextEchoMode(QLineEdit.EchoMode.Normal)
        dialog.setTextValue(prefill)

        field = dialog.findChild(QLineEdit)
        if field is not None:
            field.setMinimumWidth(_CHAT_TITLE_FIELD_WIDTH)

        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.textValue(), accepted

    def confirm_delete_chat(self, chat_id: str, chat_title: str):
        answer = QMessageBox.question(
            self,
            "Delete chat",
            f'Delete "{chat_title}" and all of its messages?\n\n'
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.chat_delete_requested.emit(chat_id)

    def scroll_to_bottom(self):
        if self.chat_scroll_area:
            self.chat_scroll_area.verticalScrollBar().setValue(
                self.chat_scroll_area.verticalScrollBar().maximum())


class RegistrationPage(QWidget):

    registration_submitted = Signal(dict)
    switch_to_login = Signal()

    def __init__(self):
        super().__init__()

        outer_layout = QVBoxLayout(self)
        outer_layout.addStretch(1)

        self.frame = QFrame()
        self.frame.setObjectName("card")
        apply_card_shadow(self.frame)
        # Wide enough for the longest button label ("Create a new account")
        self.frame.setMinimumWidth(440)
        self.frame.setMaximumWidth(520)

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
        self.register_button.setMaximumHeight(40)

        self.login_button = QPushButton("Back to sign in")
        self.login_button.setMaximumHeight(40)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.register_button)
        button_layout.addWidget(self.login_button)
        button_layout.addStretch(1)

        self.main_title = QLabel("AI-assistant")
        self.main_title.setObjectName("app_title")
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


class LoginPage(QWidget):
    login_submitted = Signal(dict)
    switch_to_registration = Signal()

    def __init__(self):
        super().__init__()

        outer_layout = QVBoxLayout(self)
        outer_layout.addStretch(1)

        self.frame = QFrame()
        self.frame.setObjectName("card")
        apply_card_shadow(self.frame)
        # Wide enough for the longest button label ("Create a new account")
        self.frame.setMinimumWidth(440)
        self.frame.setMaximumWidth(520)

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
        self.login_button.setMaximumHeight(40)

        self.register_button = QPushButton("Create a new account")
        self.register_button.setMaximumHeight(40)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.register_button)
        button_layout.addStretch(1)

        self.main_title = QLabel("AI-assistant")
        self.main_title.setObjectName("app_title")
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
