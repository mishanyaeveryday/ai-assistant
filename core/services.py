import bcrypt
from datetime import datetime
from config.settings import BUILTIN_MCP_SERVERS
from core.crypto import SecretBox, referenced_names, scrub, secret_ref, substitute
from core.models import User, Chat, MessageHistory, MCPServer
from db.database import User_DB, Chat_DB, MessageHistory_DB, MCPServer_DB, Secret_DB


class AuthService:
    def __init__(self, user_db: User_DB):
        self.user_db = user_db

    def _hash_password(self, password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, stored_password_hash, provided_password):
        return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password_hash.encode('utf-8'))

    def register_user(self, username, email, password):
        if self.user_db.get_user_by_username(username):
            return (False, f'Username {username} is already taken.')

        if self.user_db.get_user_by_email(email):
            return (False, f'Email {email} is already taken.')

        if len(password) < 8:
            return (False, 'Password is too short.')

        hashed_password = self._hash_password(password)

        new_user_data = self.user_db.add_user(
            username=username,
            email=email,
            password=hashed_password
        )

        if new_user_data:
            return (True, "Registration was successful!")
        else:
            return (False, "Could not create a user in the database.")

    def login_user(self, username, password):
        user_data = self.user_db.get_user_by_username(
            username)

        if user_data and self.check_password(stored_password_hash=user_data['password'], provided_password=password):
            user_object = User.from_db_row(user_data)
            return True, user_object
        else:
            return False, "Invalid username or password"


class ChatService:
    def __init__(self, chat_db: Chat_DB):
        self.chat_db = chat_db

    def get_all_user_chats(self, user_id: str) -> list[Chat]:
        chats_rows = self.chat_db.get_all_chats_by_user_id(id=user_id)
        if not chats_rows:
            return []

        return [Chat.from_db_row(row) for row in chats_rows]

    def create_new_chat(self, user_id: str, chat_title: str):
        self.chat_db.add_chat(title=chat_title, user_id=user_id)

    def delete_chat(self, chat_id: str) -> bool:
        return self.chat_db.delete_chat(chat_id=chat_id)


class SecretService:
    """Stores credentials encrypted, apart from the connections that use them.
    Server rows only ever hold a ${secret:NAME} reference."""

    def __init__(self, secret_db: Secret_DB, secret_box: SecretBox = None):
        self.secret_db = secret_db
        self.secret_box = secret_box or SecretBox()

    def set_secret(self, user_id: str, name: str, value: str) -> None:
        self.secret_db.set_secret(
            user_id=user_id, name=name,
            ciphertext=self.secret_box.encrypt(value))

    def get_secret(self, user_id: str, name: str) -> str | None:
        row = self.secret_db.get_secret(user_id=user_id, name=name)
        if row is None:
            return None
        return self.secret_box.decrypt(row['ciphertext'])

    def list_names(self, user_id: str) -> list[str]:
        """Names only - values are never listed in bulk."""
        return self.secret_db.get_names_by_user_id(user_id=user_id)

    def delete_secret(self, user_id: str, name: str) -> bool:
        return self.secret_db.delete_secret(user_id=user_id, name=name)

    def resolve(self, user_id: str, value):
        """Fills in the ${secret:NAME} references in a config value.

        Returns the resolved copy plus the set of values that were filled in,
        so the caller can keep them out of whatever it stores afterwards. An
        unknown name is left as the literal reference rather than becoming an
        empty string, so a missing secret fails loudly at connect time instead
        of silently sending no credentials."""
        return substitute(value, lambda name: self.get_secret(user_id, name))


def server_secret_name(server_name: str, kind: str, key: str) -> str:
    """Name of the secret holding one env/header value of a server the user
    added. Server names cannot contain a dot, so these never collide between
    servers."""
    return f"{server_name}.{kind}.{key}"


class MCPServerService:
    def __init__(self, mcp_server_db: MCPServer_DB, secret_service: SecretService = None):
        self.mcp_server_db = mcp_server_db
        self.secret_service = secret_service

    def get_user_servers(self, user_id: str) -> list[MCPServer]:
        rows = self.mcp_server_db.get_servers_by_user_id(user_id=user_id)
        return [MCPServer.from_db_row(row) for row in rows]

    def get_enabled_servers(self, user_id: str) -> list[MCPServer]:
        return [s for s in self.get_user_servers(user_id) if s.is_enabled]

    def get_server(self, server_id: str) -> MCPServer | None:
        row = self.mcp_server_db.get_server_by_id(id=server_id)
        return MCPServer.from_db_row(row) if row else None

    def get_server_by_name(self, user_id: str, name: str) -> MCPServer | None:
        row = self.mcp_server_db.get_server_by_name(user_id=user_id, name=name)
        return MCPServer.from_db_row(row) if row else None

    def get_server_field(self, server_id: str, field: str):
        """Reads one field off a server - the hook for handing a single piece
        of a server's config to the model without loading the whole row."""
        return self.mcp_server_db.get_field(id=server_id, field=field)

    def add_stdio_server(self, user_id: str, name: str, command: str = None,
                         args: list = None, env: dict = None,
                         description: str = None) -> str | None:
        return self.mcp_server_db.add_server(
            user_id=user_id, name=name, transport=MCPServer.STDIO,
            command=command, args=args or [], env=env,
            description=description)

    def add_http_server(self, user_id: str, name: str, url: str,
                        headers: dict = None, description: str = None) -> str | None:
        return self.mcp_server_db.add_server(
            user_id=user_id, name=name, transport=MCPServer.HTTP,
            url=url, headers=headers, description=description)

    def add_user_server(self, user_id: str, name: str, transport: str,
                        command: str = None, args: list = None, env: dict = None,
                        url: str = None, headers: dict = None,
                        description: str = None) -> str | None:
        """Adds a server the user configured in settings. Every env and header
        value is moved into the encrypted secrets table first, so the row only
        ever holds ${secret:...} references - those values are where tokens go.

        Returns None if the user already has a server with this name. That is
        checked before any secret is written: a rejected duplicate must not
        overwrite the credentials of the server that already has the name."""
        if self.get_server_by_name(user_id, name) is not None:
            return None

        env = self._protect_values(user_id, name, 'env', env)
        headers = self._protect_values(user_id, name, 'header', headers)
        if transport == MCPServer.HTTP:
            return self.add_http_server(
                user_id, name, url=url, headers=headers, description=description)
        return self.add_stdio_server(
            user_id, name, command=command, args=args, env=env,
            description=description)

    def _protect_values(self, user_id: str, server_name: str, kind: str,
                        pairs: dict | None) -> dict | None:
        """Stores each plain value as a secret and returns the pairs with
        references in their place. A value that already references a secret
        is kept as written, and an empty one has nothing to hide."""
        if not pairs:
            return pairs
        protected = {}
        for key, value in pairs.items():
            if not value or referenced_names(value):
                protected[key] = value
                continue
            if self.secret_service is None:
                # Writing the value into the row instead would leave a token in
                # plain text in the database.
                raise RuntimeError(
                    "Cannot store server credentials without a secret service")
            secret_name = server_secret_name(server_name, kind, key)
            self.secret_service.set_secret(user_id, secret_name, value)
            protected[key] = secret_ref(secret_name)
        return protected

    def _owned_secret_names(self, server: MCPServer) -> list[str]:
        """Secrets that add_user_server created for this server. A reference
        the user wrote themselves points at a secret they manage, so it is
        not included."""
        names = []
        for kind, pairs in (('env', server.env), ('header', server.headers)):
            for key, value in (pairs or {}).items():
                name = server_secret_name(server.name, kind, key)
                if value == secret_ref(name):
                    names.append(name)
        return names

    def update_server(self, server_id: str, **fields) -> bool:
        return self.mcp_server_db.update_server(server_id, **fields)

    def set_server_enabled(self, server_id: str, enabled: bool) -> bool:
        return self.mcp_server_db.update_server(server_id, is_enabled=enabled)

    def delete_server(self, server_id: str) -> bool:
        """Removes the server along with the secrets created for it."""
        server = self.get_server(server_id)
        deleted = self.mcp_server_db.delete_server(id=server_id)
        if deleted and server is not None and self.secret_service is not None:
            for name in self._owned_secret_names(server):
                self.secret_service.delete_secret(server.user_id, name)
        return deleted

    async def probe_server(self, server_id: str):
        """Runs the transport-appropriate connection check and records the
        outcome. A server that fails is switched off so nothing tries to use
        it; a later successful probe switches it back on - but only if it was
        this check that disabled it, so a manual disable is not undone.

        Returns a ProbeResult, or None if there is no such server."""
        # Imported here so the rest of the services layer stays usable without
        # the MCP SDK, and so core/ does not depend on agent/ at import time.
        from agent.mcp_probe import probe

        server = self.get_server(server_id)
        if server is None:
            return None

        # Secrets are decrypted here and go no further than the probe call:
        # they are never written back to the row and never attached to the
        # MCPServer object, which callers can read field by field.
        env, used = self.resolve_secrets(server.user_id, server.env)
        headers, header_secrets = self.resolve_secrets(server.user_id, server.headers)
        used |= header_secrets

        result = await probe(
            server.transport,
            command=server.command,
            args=server.args,
            env=env,
            url=server.url,
            headers=headers,
        )

        if result.ok:
            is_enabled = server.is_enabled or server.is_broken
        else:
            is_enabled = False

        updates = {}
        if result.ok:
            # Cached so the model can be offered these tools while nothing is
            # running. A failed probe keeps the previous list rather than
            # blanking it - a server that is temporarily down is still known.
            updates['known_tools'] = list(result.tool_specs)

        self.mcp_server_db.update_server(
            server_id,
            **updates,
            last_status=MCPServer.STATUS_OK if result.ok else MCPServer.STATUS_ERROR,
            last_error_code=result.code,
            # A crashing server can echo its own environment into stderr,
            # which _tail captures - so the resolved values are stripped out
            # before the message is stored or shown.
            last_error=None if result.ok else scrub(result.message, used),
            last_checked_at=datetime.now().isoformat(),
            is_enabled=is_enabled,
        )
        return result

    async def probe_user_servers(self, user_id: str) -> dict:
        """Checks every server this user has and returns the results keyed by
        server id."""
        results = {}
        for server in self.get_user_servers(user_id):
            result = await self.probe_server(server.id)
            if result is not None:
                results[server.id] = result
        return results

    def get_tool_catalogue(self, user_id: str) -> tuple[list[dict], dict]:
        """What the model may call, taken from the cache on each enabled
        server - independent of whether anything is running right now.

        Returns the tool specs plus a map of tool name to the server that owns
        it, which is what lets a call start the right server on demand.
        """
        specs = []
        owners = {}
        for server in self.get_enabled_servers(user_id):
            for spec in server.known_tools:
                name = spec.get('name')
                if not name or name in owners:
                    # First server wins; a later one re-using the name would
                    # otherwise silently hijack the call.
                    continue
                owners[name] = server
                specs.append(spec)
        return specs, owners

    def resolve_secrets(self, user_id: str, value):
        """Fills in ${secret:NAME} references just before a connection is
        made. No secret service wired in means references are left as-is, and
        plain values configured before this existed keep working untouched."""
        if self.secret_service is None:
            return value, set()
        return self.secret_service.resolve(user_id, value)

    def get_broken_servers(self, user_id: str) -> list[MCPServer]:
        return [s for s in self.get_user_servers(user_id) if s.is_broken]

    def ensure_builtin_servers(self, user_id: str) -> int:
        """Writes the servers that ship with the app into this user's list.
        Safe to call on every login: UNIQUE(user_id, name) makes a repeat a
        no-op, so it also backfills users who registered earlier.

        `command` is left empty on purpose - the interpreter is resolved when
        the server is launched, so the rows don't go stale when the venv is
        rebuilt."""
        added = 0
        for server in BUILTIN_MCP_SERVERS:
            created = self.mcp_server_db.add_server(
                user_id=user_id,
                name=server['name'],
                transport=MCPServer.STDIO,
                args=[server['script']],
                description=server.get('description'),
                is_builtin=True,
            )
            if created:
                added += 1
        return added


class MessageService:
    def __init__(self, message_db: MessageHistory_DB):
        self.message_db = message_db

    def get_messages_from_chat(self, chat_id):
        message_rows = self.message_db.get_messages_by_chat_id(chat_id=chat_id)

        if not message_rows:
            return []

        return [MessageHistory.from_db_row(row) for row in message_rows]


class AIClientService():
    def __init__(self, message_db: MessageHistory_DB):
        self.message_db = message_db

    def record_input(self, input, chat_id):
        id = self.message_db.add_input(chat_id=chat_id, user_input=input)
        return id

    def record_output(self, id, output, chat_id):
        self.message_db.add_output(
            message_history_id=id, chat_id=chat_id, assistant_output=output)

    def record_conversation(self, input, output, chat_id):
        self.message_db.add_input_and_output(
            chat_id=chat_id, user_input=input, assistant_output=output)

    def load_memory_for_chat(self, chat_id):
        message_history = self.message_db.get_last_5_messages_by_id(
            chat_id=chat_id)
        print(f"Message hstr: {message_history}")
        # # add memory
        # # Summarize messages: Summarize earlier messages in the history and replace them with a summary
        # # Manage checkpoints to store and retrieve message history
        # # Custom strategies (e.g., message filtering, etc.)
        memory = []
        for msg in message_history:
            user_message = msg.get('user')
            ai_message = msg.get('model')

            if user_message:
                memory.append({"input": user_message})

            if ai_message:
                memory.append({"output": ai_message})

        return memory
