import json


def _decode_json(raw, fallback):
    """The JSON-shaped columns (args/env/headers) are stored as text, so rows
    are decoded here and callers always get a real list/dict."""
    if raw is None or raw == "":
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


class User:
    def __init__(self, id, username, email, password, type_of_subscription,
                 os_type, created_at, last_active, language, history_enabled, is_active):
        self.id = id
        self.username = username
        self.email = email
        self.password = password
        self.type_of_subscription = type_of_subscription
        self.os_type = os_type
        self.created_at = created_at
        self.last_active = last_active
        self.language = language
        self.history_enabled = history_enabled
        self.is_active = is_active

    @classmethod
    def from_db_row(cls, row: dict):
        return cls(
            id=row['id'],
            username=row['username'],
            email=row['email'],
            password=row['password'],
            type_of_subscription=row['type_of_subscription'],
            os_type=row.get('os_type'),
            created_at=row.get('created_at'),
            last_active=row.get('last_active'),
            language=row.get('language'),
            history_enabled=row.get('history_enabled'),
            is_active=row.get('is_active')
        )


class Chat:
    def __init__(self, id, title, user_id, created_at):
        self.id = id
        self.title = title
        self.user_id = user_id
        self.created_at = created_at

    @classmethod
    def from_db_row(cls, row: dict):
        return cls(
            id=row['id'],
            title=row['title'],
            user_id=row['user_id'],
            created_at=row['created_at']
        )


class MCPServer:
    """One MCP server belonging to a user. `transport` decides which fields
    matter: stdio uses command/args/env, http uses url/headers."""

    STDIO = "stdio"
    HTTP = "http"

    # Values written to last_status by a connection probe.
    STATUS_OK = "ok"
    STATUS_ERROR = "error"

    def __init__(self, id, user_id, name, transport, command, args, env,
                 url, headers, description, is_builtin, is_enabled, created_at,
                 last_status=None, last_error_code=None, last_error=None,
                 last_checked_at=None, known_tools=None):
        self.id = id
        self.user_id = user_id
        self.name = name
        self.transport = transport
        self.command = command
        self.args = args
        self.env = env
        self.url = url
        self.headers = headers
        self.description = description
        self.is_builtin = is_builtin
        self.is_enabled = is_enabled
        self.created_at = created_at
        self.last_status = last_status
        self.last_error_code = last_error_code
        self.last_error = last_error
        self.last_checked_at = last_checked_at
        # Tool definitions seen at the last successful probe, so the model can
        # be offered this server's tools without it being running.
        self.known_tools = known_tools or []

    @property
    def is_broken(self) -> bool:
        """True once a probe has failed and not yet succeeded again."""
        return self.last_status == self.STATUS_ERROR

    @classmethod
    def from_db_row(cls, row: dict):
        return cls(
            id=row['id'],
            user_id=row['user_id'],
            name=row['name'],
            transport=row['transport'],
            command=row.get('command'),
            args=_decode_json(row.get('args'), []),
            env=_decode_json(row.get('env'), {}),
            url=row.get('url'),
            headers=_decode_json(row.get('headers'), {}),
            description=row.get('description'),
            is_builtin=bool(row.get('is_builtin')),
            is_enabled=bool(row.get('is_enabled')),
            created_at=row.get('created_at'),
            last_status=row.get('last_status'),
            last_error_code=row.get('last_error_code'),
            last_error=row.get('last_error'),
            last_checked_at=row.get('last_checked_at'),
            known_tools=_decode_json(row.get('known_tools'), [])
        )


class MessageHistory:
    def __init__(self, id, input, output, chat_id, timestamp):
        self.id = id
        self.input = input
        self.output = output
        self.chat_id = chat_id
        self.timestamp = timestamp

    @classmethod
    def from_db_row(cls, row: dict):
        return cls(
            id=row['id'],
            input=row['input'],
            output=row['output'],
            chat_id=row['chat_id'],
            timestamp=row['timestamp']
        )
