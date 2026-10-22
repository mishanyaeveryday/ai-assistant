import asyncio
import html
import json
import re
from pathlib import Path

import shiboken6
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                               QPushButton, QLabel, QLineEdit, QFormLayout, QHBoxLayout, QFrame, QScrollArea,
                               QButtonGroup, QGraphicsDropShadowEffect, QPlainTextEdit, QStackedWidget,
                               QMessageBox, QInputDialog, QDialog, QRadioButton, QSizePolicy,
                               QFileDialog)
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtCore import Qt, Signal, QTimer, QEvent

from interface.gui.markdown_render import markdown_to_html

_IMAGE_MARKER_RE = re.compile(r"\[GENERATED_IMAGE:(.+?)\]")
_MAX_IMAGE_WIDTH = 420
_CHAT_TITLE_FIELD_WIDTH = 280
# Around the chat cells and the message box under them, so their edges line up.
_CHAT_MARGIN = 8
_COMPOSER_BUTTON_WIDTH = 76
_IMAGE_PLACEHOLDER_STYLE = (
    "color: #8a8f98; font-style: italic; background-color: #f1f8e9; "
    "border-radius: 8px; padding: 8px 10px;"
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


def build_user_bubble(text: str) -> QLabel:
    # Rich text, so the prompt is escaped and its line breaks kept.
    escaped = html.escape(text).replace("\n", "<br>")
    label = QLabel(f"<b>You:</b><br>{escaped}")
    label.setWordWrap(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setStyleSheet(
        "background-color: #e1f5fe; border-radius: 8px; padding: 8px 10px;")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    return label


def build_assistant_bubble(text: str) -> QWidget:
    clean_text, image_paths = _split_text_and_images(text)

    bubble = QWidget()
    layout = QVBoxLayout(bubble)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    if clean_text:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setOpenExternalLinks(True)
        label.setStyleSheet(
            "background-color: #f1f8e9; border-radius: 8px; padding: 8px 10px;")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # The model writes Markdown. Rendered with the label's font, which the
        # stylesheet only sets once the label is polished.
        label.ensurePolished()
        label.setText(markdown_to_html(clean_text, label.font(), title="Assistant:"))
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
    used instead of a blocking popup dialog. Once answered it folds into a
    single line, so a task that asked many times still leaves a readable chat.
    Its look lives in style.qss: a style set on the card itself would be
    inherited by every label inside it."""

    decided = Signal(bool)

    # outcome -> (status text, objectName that colours it)
    _OUTCOMES = {
        'approved': ("✓ Allowed", "approval_allowed"),
        'denied': ("✕ Denied", "approval_denied"),
        'stopped': ("Stopped", "approval_stopped"),
    }
    _MAX_DETAILS_LINES = 8
    _SUMMARY_CHARS = 80

    def __init__(self, tool_name: str, args: dict, parent=None):
        super().__init__(parent)
        self.is_decided = False
        # As the last cell of a short chat it would be handed the spare height.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame()
        self._card.setObjectName("approval_card")
        self._card.setProperty("decided", False)
        card_layout = QVBoxLayout(self._card)
        # Lines its text up with the messages', which sit a few pixels
        # inside their own padding.
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._title = QLabel(
            f'Allow <span style="font-family: Menlo, Consolas, monospace; font-weight: 600;">'
            f'{html.escape(tool_name)}</span> to run?')
        self._title.setTextFormat(Qt.TextFormat.RichText)
        # Shown instead of the title once answered: what ran, on one line.
        self._summary = QLabel(" ".join(filter(None, [tool_name, self._summarize(args)])))
        self._summary.setObjectName("approval_summary")
        self._summary.setTextFormat(Qt.TextFormat.PlainText)
        # Clipped rather than widening the chat when the command is long.
        self._summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._summary.setToolTip(self._format_args(args))
        self._summary.hide()
        self._status = QLabel()
        self._status.hide()
        header.addWidget(self._title, 1)
        header.addWidget(self._summary, 1)
        header.addWidget(self._status)
        card_layout.addLayout(header)

        details_text = self._format_args(args)
        self._details = QPlainTextEdit(details_text)
        self._details.setObjectName("approval_details")
        self._details.setReadOnly(True)
        self._details.setFixedHeight(self._details_height(details_text))
        card_layout.addWidget(self._details)

        self._buttons = QWidget()
        self._buttons.setObjectName("approval_buttons")
        button_row = QHBoxLayout(self._buttons)
        button_row.setContentsMargins(0, 0, 0, 0)
        deny_button = QPushButton("Deny")
        deny_button.setObjectName("secondary_button")
        approve_button = QPushButton("Allow")
        button_row.addStretch(1)
        button_row.addWidget(deny_button)
        button_row.addWidget(approve_button)
        card_layout.addWidget(self._buttons)

        approve_button.clicked.connect(lambda: self._resolve(True))
        deny_button.clicked.connect(lambda: self._resolve(False))

        outer.addWidget(self._card)

    def _details_height(self, text: str) -> int:
        lines = min(text.count("\n") + 1, self._MAX_DETAILS_LINES)
        return lines * self._details.fontMetrics().lineSpacing() + 18

    @staticmethod
    def _value_text(value) -> str:
        return value if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, default=str)

    @classmethod
    def _format_args(cls, args: dict) -> str:
        if not args:
            return "(no arguments)"
        lines = []
        for key, value in args.items():
            text = cls._value_text(value)
            if "\n" in text:
                lines.append(f"{key}:")
                lines.extend(f"  {line}" for line in text.splitlines())
            else:
                lines.append(f"{key}: {text}")
        return "\n".join(lines)

    @classmethod
    def _summarize(cls, args: dict) -> str:
        """The first argument on one line - usually what the call is about,
        e.g. the command or the path."""
        if not args:
            return ""
        text = " ".join(cls._value_text(next(iter(args.values()))).split())
        if len(text) > cls._SUMMARY_CHARS:
            text = text[:cls._SUMMARY_CHARS - 1] + "…"
        return text

    def _resolve(self, approved: bool):
        if self.is_decided:
            return
        self.show_outcome('approved' if approved else 'denied')
        self.decided.emit(approved)

    def mark_stopped(self):
        """The task was stopped while this was still waiting for an answer."""
        if not self.is_decided:
            self.show_outcome('stopped')

    def show_outcome(self, outcome: str):
        """Folds the card into its answered form, without asking again."""
        self.is_decided = True
        text, name = self._OUTCOMES[outcome]
        self._status.setText(text)
        self._status.setObjectName(name)
        self._title.hide()
        self._details.hide()
        self._buttons.hide()
        self._summary.show()
        self._status.show()
        self._card.setProperty("decided", True)
        # A changed property or objectName only restyles once re-polished.
        for widget in (self._card, self._status):
            widget.style().unpolish(widget)
            widget.style().polish(widget)


class PromptInput(QPlainTextEdit):
    """The message box: grows with its text up to a few lines. Enter sends,
    Shift+Enter starts a new line."""

    submitted = Signal()

    _MAX_VISIBLE_LINES = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("prompt_input")
        self.setPlaceholderText("Ask anything")
        self.setTabChangesFocus(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The stylesheet's font, border and padding are only applied when the
        # widget is polished; measured before that, every height is off.
        self.ensurePolished()
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self._fit_height()

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._fit_height()

    def height_for_lines(self, lines: int) -> int:
        margins = self.contentsMargins()          # the stylesheet's border + padding
        # The few extra pixels are what a line takes beyond its spacing; a
        # height without them scrolls by one line.
        return int(lines * self.fontMetrics().lineSpacing()
                   + 2 * self.document().documentMargin() + 4
                   + margins.top() + margins.bottom())

    def _fit_height(self, *_):
        # The plain-text layout measures the document in lines, wrapped ones
        # included.
        lines = int(self.document().documentLayout().documentSize().height())
        overflowing = lines > self._MAX_VISIBLE_LINES
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if overflowing
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(self.height_for_lines(min(max(lines, 1), self._MAX_VISIBLE_LINES)))


class ElidedLabel(QLabel):
    """One line of text cut short with … when it does not fit; the full text
    is in the tooltip. A plain label would instead widen its whole panel to
    fit a long line. Paths are cut from the left, so the folder's own name
    stays."""

    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._mode = mode
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str):
        self._full_text = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(
            self._full_text, self._mode, self.width()))


def _display_path(path: str) -> str:
    home = str(Path.home())
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


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


def _plain_label(text: str = "") -> QLabel:
    """Server names, descriptions and errors come from outside the app; plain
    text mode stops QLabel from reading a traceback's `<...>` as markup."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class MCPServersSection(QFrame):
    """Settings section listing the user's MCP servers. Adding one happens in
    an inline form rather than a dialog, like the rest of the settings page."""

    add_requested = Signal(dict)
    delete_requested = Signal(str)
    enabled_changed = Signal(str, bool)
    check_requested = Signal(str)
    # (server id, tool name, allowed): let the tool run without asking.
    auto_approve_changed = Signal(str, str, bool)
    # Shown again - the controller re-reads the list so statuses are current.
    opened = Signal()

    _STATUS_COLORS = {
        'ok': '#2e7d32',
        'error': '#c62828',
        'checking': '#3d5afe',
        'off': '#8a8f98',
        'unchecked': '#8a8f98',
    }

    def __init__(self):
        super().__init__()
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QHBoxLayout()
        heading = QLabel("MCP servers")
        heading.setObjectName("section_label")
        self.add_button = QPushButton("+ Add server")
        self.add_button.clicked.connect(self.open_form)
        header.addWidget(heading)
        header.addStretch(1)
        header.addWidget(self.add_button)
        layout.addLayout(header)

        self.form = self._build_form()
        self.form.hide()
        layout.addWidget(self.form)

        self.rows_container = QWidget()
        self.rows_container.setObjectName("server_list")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        layout.addWidget(self.rows_container)

        # Every refresh rebuilds the rows - and checks refresh them several
        # times on login - so which tool lists are open is kept here.
        self._servers: list[dict] = []
        self._expanded: set[str] = set()

    def showEvent(self, event):
        super().showEvent(event)
        self.opened.emit()

    def _build_form(self) -> QFrame:
        form = QFrame()
        form.setObjectName("server_form")
        form_outer = QVBoxLayout(form)
        form_outer.setContentsMargins(14, 12, 14, 12)
        form_outer.setSpacing(8)

        self.form_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("github")

        transport_row = QWidget()
        transport_row.setObjectName("server_list")
        transport_layout = QHBoxLayout(transport_row)
        transport_layout.setContentsMargins(0, 0, 0, 0)
        self.stdio_radio = QRadioButton("Local command (stdio)")
        self.http_radio = QRadioButton("URL (http)")
        self.stdio_radio.setChecked(True)
        self.transport_group = QButtonGroup(form)
        self.transport_group.addButton(self.stdio_radio)
        self.transport_group.addButton(self.http_radio)
        self.stdio_radio.toggled.connect(self._update_transport_rows)
        transport_layout.addWidget(self.stdio_radio)
        transport_layout.addWidget(self.http_radio)
        transport_layout.addStretch(1)

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText(
            "npx -y @modelcontextprotocol/server-github")

        self.env_input = QPlainTextEdit()
        self.env_input.setObjectName("form_text")
        self.env_input.setPlaceholderText("GITHUB_TOKEN=ghp_...\nOne KEY=value per line")
        self.env_input.setFixedHeight(64)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/mcp")

        self.headers_input = QPlainTextEdit()
        self.headers_input.setObjectName("form_text")
        self.headers_input.setPlaceholderText(
            "Authorization: Bearer ...\nOne Name: value per line")
        self.headers_input.setFixedHeight(64)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Optional")

        self.form_layout.addRow("Name:", self.name_input)
        self.form_layout.addRow("Type:", transport_row)
        self.form_layout.addRow("Command:", self.command_input)
        self.form_layout.addRow("Environment:", self.env_input)
        self.form_layout.addRow("URL:", self.url_input)
        self.form_layout.addRow("Headers:", self.headers_input)
        self.form_layout.addRow("Description:", self.description_input)
        form_outer.addLayout(self.form_layout)

        hint = QLabel("Put tokens in Environment or Headers - those values are "
                      "stored encrypted. The command is stored as plain text.")
        hint.setObjectName("hint_text")
        hint.setWordWrap(True)
        form_outer.addWidget(hint)

        self.form_error = _plain_label()
        self.form_error.setObjectName("error_text")
        self.form_error.setWordWrap(True)
        self.form_error.hide()
        form_outer.addWidget(self.form_error)

        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondary_button")
        cancel_button.clicked.connect(self.close_form)
        self.submit_button = QPushButton("Add server")
        self.submit_button.clicked.connect(self._submit_form)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(self.submit_button)
        form_outer.addLayout(buttons)

        self._update_transport_rows()
        return form

    def _update_transport_rows(self):
        is_stdio = self.stdio_radio.isChecked()
        # An error about the other type's fields no longer applies.
        self.form_error.hide()
        self.form_layout.setRowVisible(self.command_input, is_stdio)
        self.form_layout.setRowVisible(self.env_input, is_stdio)
        self.form_layout.setRowVisible(self.url_input, not is_stdio)
        self.form_layout.setRowVisible(self.headers_input, not is_stdio)

    def open_form(self):
        self.form.show()
        self.add_button.hide()
        self.name_input.setFocus()

    def close_form(self):
        for field in (self.name_input, self.command_input, self.url_input,
                      self.description_input, self.env_input, self.headers_input):
            field.clear()
        self.stdio_radio.setChecked(True)
        self.form_error.hide()
        self.form.hide()
        self.add_button.show()

    def show_form_error(self, text: str):
        self.form_error.setText(text)
        self.form_error.show()

    def _submit_form(self):
        self.form_error.hide()
        self.add_requested.emit({
            'name': self.name_input.text(),
            'transport': 'stdio' if self.stdio_radio.isChecked() else 'http',
            'command': self.command_input.text(),
            'env': self.env_input.toPlainText(),
            'url': self.url_input.text(),
            'headers': self.headers_input.toPlainText(),
            'description': self.description_input.text(),
        })

    def show_servers(self, servers: list[dict]):
        self._servers = servers
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget() is not None:
                # Hidden first: until deleteLater gets to it, an old row would
                # still paint under the new ones - which now differ in height
                # whenever a tool list is opened or closed.
                item.widget().hide()
                item.widget().deleteLater()

        if not servers:
            empty = QLabel("No servers yet.")
            empty.setObjectName("placeholder_text")
            self.rows_layout.addWidget(empty)
            return

        for server in servers:
            self.rows_layout.addWidget(self._build_row(server))

    def _build_row(self, server: dict) -> QFrame:
        server_id = server['id']
        checking = server['status'] == 'checking'
        expanded = server_id in self._expanded

        row = QFrame()
        row.setObjectName("server_row")
        outer_layout = QVBoxLayout(row)
        outer_layout.setContentsMargins(12, 10, 12, 10)
        outer_layout.setSpacing(10)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(10)
        outer_layout.addLayout(row_layout)

        info = QVBoxLayout()
        info.setSpacing(2)

        title_line = QHBoxLayout()
        title_line.setSpacing(6)
        name = _plain_label(server['name'])
        name.setObjectName("server_name")
        title_line.addWidget(name)
        tags = [server['transport']] + (['built-in'] if server['is_builtin'] else [])
        for tag in tags:
            tag_label = QLabel(tag)
            tag_label.setObjectName("server_tag")
            title_line.addWidget(tag_label)
        title_line.addStretch(1)
        info.addLayout(title_line)

        if server['detail']:
            detail = _plain_label(server['detail'])
            detail.setObjectName("hint_text")
            detail.setToolTip(server['target'])
            info.addWidget(detail)

        status = _plain_label(self._status_text(server))
        status.setWordWrap(True)
        status.setStyleSheet(
            f"color: {self._STATUS_COLORS[server['status']]}; font-size: 12px;")
        if server['status'] == 'error' and server['error']:
            status.setToolTip(server['error'])
        info.addWidget(status)
        row_layout.addLayout(info, 1)

        tools_button = QPushButton("Hide tools" if expanded else "Tools")
        tools_button.setObjectName("secondary_button")
        tools_button.setToolTip("Choose which of its tools may run without asking")
        tools_button.setMinimumWidth(110)
        tools_button.clicked.connect(
            lambda _, sid=server_id: self._toggle_tools(sid))
        row_layout.addWidget(tools_button)

        # While a check runs its result is about to overwrite the row, so the
        # controls that change the row wait for it.
        enabled_button = QPushButton("Enabled" if server['is_enabled'] else "Disabled")
        enabled_button.setObjectName("toggle_button")
        enabled_button.setCheckable(True)
        enabled_button.setChecked(server['is_enabled'])
        enabled_button.setToolTip("Click to turn this server off" if server['is_enabled']
                                  else "Click to turn this server on")
        enabled_button.setMinimumWidth(100)
        enabled_button.setEnabled(not checking)
        enabled_button.toggled.connect(
            lambda checked, sid=server_id: self.enabled_changed.emit(sid, checked))
        row_layout.addWidget(enabled_button)

        check_button = QPushButton("Checking…" if checking else "Check")
        check_button.setObjectName("secondary_button")
        check_button.setMinimumWidth(110)
        check_button.setEnabled(not checking)
        check_button.clicked.connect(
            lambda _, sid=server_id: self.check_requested.emit(sid))
        row_layout.addWidget(check_button)

        if server['is_builtin']:
            # Keeps the buttons lined up with the rows that have a delete button.
            row_layout.addSpacing(24)
        else:
            delete_button = QPushButton("✕")
            delete_button.setObjectName("chat_delete_button")
            delete_button.setToolTip(f'Delete "{server["name"]}"')
            delete_button.setFixedSize(24, 24)
            delete_button.setEnabled(not checking)
            delete_button.clicked.connect(
                lambda _, sid=server_id, title=server['name']: self.confirm_delete(sid, title))
            row_layout.addWidget(delete_button)

        if expanded:
            outer_layout.addWidget(self._build_tools_panel(server))

        return row

    def _toggle_tools(self, server_id: str):
        if server_id in self._expanded:
            self._expanded.discard(server_id)
        else:
            self._expanded.add(server_id)
        self.show_servers(self._servers)

    def _build_tools_panel(self, server: dict) -> QFrame:
        """The server's tools, each with whether it asks before running."""
        panel = QFrame()
        panel.setObjectName("tools_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        tools = server['tool_list']
        if not tools:
            empty = QLabel("Check the server to see its tools.")
            empty.setObjectName("hint_text")
            layout.addWidget(empty)
            return panel

        hint = QLabel("An allowed tool runs as soon as the model calls it - no card "
                      "in the chat to stop it. Allow only what you trust it to do on its own.")
        hint.setObjectName("hint_text")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for tool in tools:
            layout.addWidget(self._build_tool_line(server['id'], tool))
        return panel

    def _build_tool_line(self, server_id: str, tool: dict) -> QWidget:
        line = QWidget()
        line.setObjectName("server_list")
        line_layout = QHBoxLayout(line)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(0)
        name = _plain_label(tool['name'])
        name.setObjectName("tool_name")
        text.addWidget(name)
        description = tool['description']
        if description:
            # One line, the rest in the tooltip: some tools come with a whole
            # paragraph.
            summary = ElidedLabel(description.splitlines()[0])
            summary.setObjectName("hint_text")
            summary.setToolTip(description)
            text.addWidget(summary)
        line_layout.addLayout(text, 1)

        if tool['shadowed_by']:
            # The model reaches the other server's tool by this name, so a
            # switch here would do nothing.
            note = _plain_label(f'Used from "{tool["shadowed_by"]}"')
            note.setObjectName("hint_text")
            line_layout.addWidget(note)
        elif not tool['asks_by_default']:
            note = QLabel("Never asks")
            note.setObjectName("hint_text")
            note.setToolTip("This tool runs without asking anyway.")
            line_layout.addWidget(note)
        else:
            allowed = tool['auto_approved']
            switch = QPushButton("Runs without asking" if allowed else "Asks first")
            switch.setObjectName("toggle_button")
            switch.setCheckable(True)
            switch.setChecked(allowed)
            switch.setMinimumWidth(170)
            switch.setToolTip("Click to make it ask first again" if allowed
                              else "Click to let it run without asking")
            switch.toggled.connect(
                lambda checked, sid=server_id, tool_name=tool['name']:
                    self.auto_approve_changed.emit(sid, tool_name, checked))
            line_layout.addWidget(switch, 0, Qt.AlignmentFlag.AlignTop)
        return line

    @staticmethod
    def _status_text(server: dict) -> str:
        status = server['status']
        if status == 'checking':
            return "Checking connection…"
        if status == 'error':
            first_line = (server['error'] or "").strip().splitlines()
            reason = f": {first_line[0]}" if first_line else ""
            return f"Unavailable ({server['error_code']}){reason}"
        if status == 'ok':
            return f"Connected · {server['tools']} tool(s)"
        if status == 'off':
            return "Turned off"
        return "Not checked yet"

    def confirm_delete(self, server_id: str, server_name: str):
        answer = QMessageBox.question(
            self,
            "Delete server",
            f'Delete the MCP server "{server_name}"?\n\n'
            "Its stored credentials are deleted too.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(server_id)


class ChatPage(QWidget):
    logout_requested = Signal()
    chat_selected = Signal(str)
    chat_delete_requested = Signal(str)
    new_chat_requested = Signal(str)
    settings_requested = Signal()
    send_input = Signal(str, str)
    stop_requested = Signal()
    # A chat was (re)built from history; whatever a running task holds that
    # history doesn't - its approval cards - has to be added back.
    chat_shown = Signal(str)
    # (chat id, folder) - an empty folder puts the chat back on the default.
    workspace_change_requested = Signal(str, str)

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
        self.chat_busy_dots = {}
        self.chats_button_group = None
        self.messages_layout = None
        self.chat_scroll_area = None
        self.message_input = None
        self.send_button = None
        self.stop_button = None
        self.busy_hint_label = None
        self.thinking_label = None
        self.workspace_label = None
        self.workspace_change_button = None
        self.workspace_reset_button = None
        self._workspace_path = None
        self.current_chat_id = None

        # Kept here rather than on the chat's widgets, which are rebuilt
        # whenever another chat is opened while the task keeps running.
        self._busy_chat_id = None
        # The open chat's approval cards, to tell whether one still waits.
        self._approval_bubbles = []
        self._thinking_dots = 0
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(450)
        self._thinking_timer.timeout.connect(self._tick_thinking)

    def set_user_data(self, user_data: dict):
        self.welcome_label.setText(f"Welcome, {user_data['username']}!")

    def _clear_right_panel(self):
        """Tears down whatever the right panel is showing and drops every
        reference to it. The widgets are gone on the C++ side after this, so
        the attributes must not keep pointing at them."""
        for i in reversed(range(self.right_panel_layout.count())):
            item = self.right_panel_layout.takeAt(i)
            if item.widget():
                # Hidden first: until deleteLater gets to it, it would still
                # paint under the chat that replaces it.
                item.widget().hide()
                item.widget().deleteLater()

        self._thinking_timer.stop()
        self.messages_layout = None
        self.chat_scroll_area = None
        self.message_input = None
        self.send_button = None
        self.stop_button = None
        self.busy_hint_label = None
        self.thinking_label = None
        self.workspace_label = None
        self.workspace_change_button = None
        self.workspace_reset_button = None
        self._workspace_path = None
        self._approval_bubbles = []

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
        self.messages_layout.setContentsMargins(_CHAT_MARGIN, _CHAT_MARGIN, _CHAT_MARGIN, _CHAT_MARGIN)
        self.messages_layout.setSpacing(10)
        self.messages_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop)
        for m in message_data:
            self.messages_layout.addWidget(build_user_bubble(m['input']))
            # A prompt that is still being worked on has no answer yet.
            if m['output'] is not None:
                self.messages_layout.addWidget(build_assistant_bubble(m['output']))

        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(chat_container)
        self.chat_scroll_area.setStyleSheet("border: none;")

        self.message_input = PromptInput()
        self.message_input.submitted.connect(self.send_prompt)
        self.message_input.textChanged.connect(self._apply_task_state)
        self.send_button = QPushButton("Send")
        self.send_button.setToolTip("Send (Enter)")
        self.send_button.clicked.connect(self.send_prompt)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stop_button")
        self.stop_button.clicked.connect(self.stop_requested.emit)
        # Level with a one-line message box, and the same width as each
        # other, so swapping one for the other doesn't move anything.
        for button in (self.send_button, self.stop_button):
            button.setFixedSize(_COMPOSER_BUTTON_WIDTH, self.message_input.height_for_lines(1))
        # The macOS style gives buttons and text boxes invisible margins that
        # layouts line up instead of the drawn edges - here that put Send
        # 8px below the box. Line up what is drawn.
        for widget in (self.message_input, self.send_button, self.stop_button):
            widget.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)

        self.busy_hint_label = QLabel()
        self.busy_hint_label.setObjectName("hint_text")
        self.busy_hint_label.hide()

        # The input row lives in its own widget rather than a bare sub-layout:
        # the panel is torn down widget by widget, and a plain layout would be
        # skipped there, leaving the old input box painted over the panel.
        bottom_row = QWidget()
        # Only as tall as it needs; the chat above takes the rest.
        bottom_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        bottom_layout = QVBoxLayout(bottom_row)
        # Lined up with the chat cells above, which sit inside the same margin.
        bottom_layout.setContentsMargins(_CHAT_MARGIN, 0, _CHAT_MARGIN, _CHAT_MARGIN)
        bottom_layout.setSpacing(4)
        bottom_layout.addWidget(self.busy_hint_label)
        bottom_layout.addWidget(self._build_workspace_bar())
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        input_row.addWidget(self.message_input, 1)
        # At the bottom, so a message box grown to several lines keeps its
        # button on its last line.
        input_row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)
        input_row.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignBottom)
        bottom_layout.addLayout(input_row)

        self.right_panel_layout.addWidget(self.chat_scroll_area, 1)
        self.right_panel_layout.addWidget(bottom_row)

        if self._busy_chat_id == chat_id:
            self._show_thinking()
        self._apply_task_state()
        self.scroll_to_bottom()
        self.message_input.setFocus()
        self.chat_shown.emit(chat_id)

    def _build_workspace_bar(self) -> QWidget:
        """The folder the open chat's tools work in, just above the message
        box. A widget of its own for the same reason as the input row: the
        panel is torn down widget by widget."""
        bar = QFrame()
        bar.setObjectName("workspace_bar")
        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 4, 4)
        layout.setSpacing(6)

        title = QLabel("Workspace:")
        title.setObjectName("hint_text")
        # Filled in by show_workspace once the controller has looked it up.
        self.workspace_label = ElidedLabel(mode=Qt.TextElideMode.ElideLeft)
        self.workspace_label.setObjectName("workspace_path")
        self.workspace_change_button = QPushButton("Change…")
        self.workspace_change_button.setObjectName("workspace_button")
        self.workspace_change_button.clicked.connect(self._pick_workspace)
        self.workspace_reset_button = QPushButton("Use default")
        self.workspace_reset_button.setObjectName("workspace_button")
        self.workspace_reset_button.setToolTip("Work in the default workspace folder again")
        self.workspace_reset_button.clicked.connect(
            lambda: self.workspace_change_requested.emit(self.current_chat_id, ""))
        self.workspace_reset_button.hide()

        layout.addWidget(title)
        layout.addWidget(self.workspace_label, 1)
        layout.addWidget(self.workspace_reset_button)
        layout.addWidget(self.workspace_change_button)
        return bar

    def show_workspace(self, chat_id: str, path: str, is_default: bool):
        if chat_id != self.current_chat_id or self.workspace_label is None:
            return
        self._workspace_path = path
        shown = _display_path(path)
        self.workspace_label.set_full_text(f"{shown} (default)" if is_default else shown)
        self.workspace_reset_button.setVisible(not is_default)

    def _pick_workspace(self):
        chat_id = self.current_chat_id
        if chat_id is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Workspace folder for this chat", self._workspace_path or str(Path.home()))
        if folder:
            self.workspace_change_requested.emit(chat_id, folder)

    def show_workspace_error(self, text: str):
        QMessageBox.warning(self, "Workspace", text)

    def set_busy_chat(self, chat_id: str | None):
        """Which chat has a task running, if any. Only one runs at a time, so
        sending is locked in every chat while it does; its own chat shows
        Stop and a thinking line instead."""
        self._busy_chat_id = chat_id
        for cid, dot in self.chat_busy_dots.items():
            dot.setVisible(cid == chat_id)
        if chat_id is not None and chat_id == self.current_chat_id:
            self._show_thinking()
        else:
            self._hide_thinking()
        self._apply_task_state()

    def _apply_task_state(self):
        # The chat can be closed (deleted) while a request is still in flight,
        # in which case these widgets no longer exist.
        if self.send_button is None or not shiboken6.isValid(self.send_button):
            return
        busy_here = self._busy_chat_id is not None and self._busy_chat_id == self.current_chat_id
        busy_elsewhere = self._busy_chat_id is not None and not busy_here

        self.send_button.setVisible(not busy_here)
        self.stop_button.setVisible(busy_here)
        # The running task keeps the folder it started with; changing it
        # here would only make the bar disagree with what the task works on.
        self.workspace_change_button.setEnabled(not busy_here)
        self.workspace_reset_button.setEnabled(not busy_here)
        has_text = bool(self.message_input.toPlainText().strip())
        self.send_button.setEnabled(has_text and self._busy_chat_id is None)

        if busy_elsewhere:
            busy_button = self.chat_buttons.get(self._busy_chat_id)
            name = f'"{busy_button.text()}"' if busy_button is not None else "Another chat"
            self.busy_hint_label.setText(
                f"{name} is still working - wait for it, or open it to stop it.")
        self.busy_hint_label.setVisible(busy_elsewhere)

    def send_prompt(self):
        if self.message_input is None or self.current_chat_id is None:
            return
        # One task at a time: Enter does nothing while one is running.
        if self._busy_chat_id is not None:
            return
        prompt_text = self.message_input.toPlainText().strip()
        if not prompt_text:
            return

        self.add_user_message(prompt_text)
        self.message_input.clear()
        self.send_input.emit(self.current_chat_id, prompt_text)

    def _append(self, widget: QWidget):
        """Adds a cell to the open chat, above the thinking line if shown."""
        index = (self.messages_layout.indexOf(self.thinking_label)
                 if self.thinking_label is not None else -1)
        if index >= 0:
            self.messages_layout.insertWidget(index, widget)
        else:
            self.messages_layout.addWidget(widget)
        self.scroll_to_bottom()

    def add_user_message(self, text: str):
        if self.messages_layout is not None:
            self._append(build_user_bubble(text))

    def add_assistant_message(self, text: str):
        if self.messages_layout is not None:
            self._append(build_assistant_bubble(text))

    def add_approval_request(self, tool_name: str, args: dict,
                             outcome: str | None = None) -> ApprovalBubble:
        """A card asking to allow a tool call - or, with `outcome`, one that
        was already answered, when an open task's chat is shown again."""
        bubble = ApprovalBubble(tool_name, args)
        if outcome is not None:
            bubble.show_outcome(outcome)
        else:
            bubble.decided.connect(lambda _: self._update_thinking_text())
        self._approval_bubbles.append(bubble)
        if self.messages_layout is not None:
            self._append(bubble)
        self._update_thinking_text()
        return bubble

    def _show_thinking(self):
        if self.messages_layout is None or self.thinking_label is not None:
            return
        self.thinking_label = QLabel()
        self.thinking_label.setObjectName("thinking_text")
        self.messages_layout.addWidget(self.thinking_label)
        self._thinking_dots = 0
        self._update_thinking_text()
        self._thinking_timer.start()
        self.scroll_to_bottom()

    def _hide_thinking(self):
        self._thinking_timer.stop()
        label, self.thinking_label = self.thinking_label, None
        if label is not None and shiboken6.isValid(label):
            label.hide()
            self.messages_layout.removeWidget(label)
            label.deleteLater()

    def _tick_thinking(self):
        self._thinking_dots = (self._thinking_dots + 1) % 4
        self._update_thinking_text()

    def _update_thinking_text(self):
        if self.thinking_label is None or not shiboken6.isValid(self.thinking_label):
            return
        waiting = any(shiboken6.isValid(b) and not b.is_decided
                      for b in self._approval_bubbles)
        text = "Waiting for your approval" if waiting else "Thinking"
        self.thinking_label.setText(text + "." * self._thinking_dots)

    def update_chats_list(self, chats_data: list[dict]):
        while self.chats_layout.count():
            item = self.chats_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.chat_buttons.clear()
        self.chat_busy_dots.clear()
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

            busy_dot = QLabel("●")
            busy_dot.setObjectName("chat_busy_dot")
            busy_dot.setToolTip("Working on a task")
            busy_dot.setVisible(chat_id == self._busy_chat_id)

            row_layout.addWidget(button, 1)
            row_layout.addWidget(busy_dot)
            row_layout.addWidget(delete_button)

            self.chats_layout.addWidget(row)
            self.chat_buttons[chat_id] = button
            self.chat_busy_dots[chat_id] = busy_dot

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
        area = self.chat_scroll_area
        if area is None:
            return

        def scroll():
            if shiboken6.isValid(area):
                area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())

        # A cell added just now is laid out on the next pass of the event
        # loop; scrolling right away would stop one cell short of it.
        QTimer.singleShot(0, scroll)


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
