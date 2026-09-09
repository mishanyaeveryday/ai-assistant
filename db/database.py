from core.models import User, Chat, MessageHistory
import json
import sqlite3
import uuid
from datetime import datetime, timedelta

# Column names are interpolated into SELECT/UPDATE for the "give me any field"
# lookups, which cannot be parameterised - so they are whitelisted here.
MCP_SERVER_COLUMNS = frozenset({
    'id', 'user_id', 'name', 'transport', 'command', 'args', 'env',
    'url', 'headers', 'description', 'is_builtin', 'is_enabled', 'created_at',
    'last_status', 'last_error_code', 'last_error', 'last_checked_at',
    'known_tools',
})
# Columns added after the table first shipped; create_table backfills them so
# a database made by an earlier run keeps working.
MCP_SERVER_ADDED_COLUMNS = (
    ('known_tools', 'TEXT'),
    ('last_status', 'TEXT'),
    ('last_error_code', 'TEXT'),
    ('last_error', 'TEXT'),
    ('last_checked_at', 'TEXT'),
)
MCP_SERVER_EDITABLE_COLUMNS = MCP_SERVER_COLUMNS - {'id', 'user_id', 'created_at'}
MCP_SERVER_JSON_COLUMNS = frozenset({'args', 'env', 'headers', 'known_tools'})
MCP_SERVER_TRANSPORTS = frozenset({'stdio', 'http'})


class User_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def _get_connection(self):
        return sqlite3.connect(self.db_name)

    def _row_to_dict(self, cursor, row):
        if row is None:
            return None
        return {desc[0]: value for desc, value in zip(cursor.description, row)}

    def create_table(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        type_of_subscription TEXT,
                        os_type TEXT,
                        created_at TEXT,
                        last_active TEXT,
                        language TEXT DEFAULT "eng",
                        history_enabled INTEGER,
                        is_active INTEGER
            )""")
            conn.commit()

    def add_user(self, username, email, password):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            id = str(uuid.uuid4())
            try:
                cursor.execute("""
                INSERT INTO users (id, username, email, password)
                VALUES (?,?,?,?)
    """, (id, username, email, password))
                conn.commit()
                return id
            except sqlite3.IntegrityError:
                return None

    def get_all_users(self):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_user_by_username(self, username):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM users WHERE username = ?', (username,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_user_by_id(self, id):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM users WHERE id = ?', (id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_user_by_email(self, email):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM users WHERE email = ?', (email,))
            result = cursor.fetchone()
            return dict(result) if result else None


class Chat_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def _get_connection(self):
        return sqlite3.connect(self.db_name)

    def _row_to_dict(self, cursor, row):
        if row is None:
            return None
        return {desc[0]: value for desc, value in zip(cursor.description, row)}

    def create_table(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    user_id TEXT,
                    created_at TEXT
                )
            """)
            conn.commit()

    def get_all_chats_by_user_id(self, id):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                'SELECT * FROM chats WHERE user_id = ?', (id,))

            rows = cursor.fetchall()
            if not rows:
                return []

            columns = [description[0]
                       for description in cursor.description]

            chats_list = [dict(zip(columns, row)) for row in rows]

            return chats_list

    def add_chat(self, title=None, user_id=None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()
            try:
                cursor.execute("""
                INSERT INTO chats (id, title, user_id, created_at)
                VALUES (?,?,?,?)
    """, (id, title, user_id, created_at))
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError("Chat with this ID already exists.")

    def delete_chat(self, chat_id):
        """Removes the chat together with its message history. Both tables
        live in the same database file, so a single transaction keeps them
        from drifting apart and leaving orphaned messages behind."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM messages_history WHERE chat_id = ?', (chat_id,))
            cursor.execute('DELETE FROM chats WHERE id = ?', (chat_id,))
            deleted = cursor.rowcount
            conn.commit()
        return deleted > 0


class MessageHistory_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def _get_connection(self):
        return sqlite3.connect(self.db_name)

    def _row_to_dict(self, cursor, row):
        if row is None:
            return None
        return {desc[0]: value for desc, value in zip(cursor.description, row)}

    def create_table(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages_history (
                    id TEXT PRIMARY KEY,
                    input TEXT,
                    output TEXT,
                    chat_id TEXT NOT NULL,
                    timestamp TEXT
                )
            """)
            conn.commit()

    def get_all_messages(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM messages_history')
            rows = cursor.fetchall()
        if rows:
            return [MessageHistory(*row) for row in rows]
        return []

    def get_messages_by_chat_id(self, chat_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM messages_history WHERE chat_id = ? ORDER BY timestamp', (chat_id,))
            rows = cursor.fetchall()
        if not rows:
            return []

        columns = [description[0]
                   for description in cursor.description]

        message_list = [dict(zip(columns, row)) for row in rows]

        return message_list

    def get_last_message(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM messages_history ORDER BY timestamp DESC LIMIT 1')
            row = cursor.fetchone()
        if row:
            return MessageHistory(*row)
        return None

    def get_last_5_messages_by_id(self, chat_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT input, output FROM messages_history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 5 ', (chat_id,))
            rows = cursor.fetchall()
            if not rows:
                return []

            messages = []
            for row in rows:
                user_text = row[0]
                model_text = row[1]
                messages.append({'user': user_text, 'model': model_text})

        messages.reverse()

        return messages

    def add_input_and_output(self, chat_id, user_input=None, assistant_output=None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            try:
                cursor.execute("""
                INSERT INTO messages_history (id, input, output, chat_id, timestamp)
                VALUES (?,?,?,?,?)
    """, (id, user_input, assistant_output, chat_id, timestamp))
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError("Message with this ID already exists.")

    def add_input(self, chat_id, user_input):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            try:
                cursor.execute("""
                INSERT INTO messages_history (id, input, chat_id, timestamp)
                VALUES (?,?,?,?)
    """, (id, user_input, chat_id, timestamp))
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError("Message with this ID already exists.")
        return id

    def add_output(self, message_history_id, chat_id, assistant_output):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            timestamp = datetime.now().isoformat()
            cursor.execute("""
            UPDATE messages_history
            SET output = ?, chat_id = ?, timestamp = ?
            WHERE id = ?
    """, (assistant_output, chat_id, timestamp, message_history_id,))
            conn.commit()

    def edit_message(self, id, user_input, assistant_output):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            values = []

            if user_input is not None:
                updates.append("input = ?")
                values.append(user_input)
            if assistant_output is not None:
                updates.append("output = ?")
                values.append(assistant_output)

            if not updates:
                raise ValueError("No new data provided for update.")

            values.append(id)

        query = f"UPDATE messages_history SET {', '.join(updates)} WHERE id = ?"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(values))
            if cursor.rowcount == 0:
                raise ValueError(f"No message found with ID: {id}")
            conn.commit()


class MCPServer_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def _get_connection(self):
        return sqlite3.connect(self.db_name)

    def _row_to_dict(self, cursor, row):
        if row is None:
            return None
        return {desc[0]: value for desc, value in zip(cursor.description, row)}

    def create_table(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    transport TEXT NOT NULL CHECK (transport IN ('stdio', 'http')),
                    command TEXT,
                    args TEXT,
                    env TEXT,
                    url TEXT,
                    headers TEXT,
                    description TEXT,
                    is_builtin INTEGER DEFAULT 0,
                    is_enabled INTEGER DEFAULT 1,
                    created_at TEXT,
                    known_tools TEXT,
                    last_status TEXT,
                    last_error_code TEXT,
                    last_error TEXT,
                    last_checked_at TEXT,
                    UNIQUE (user_id, name)
                )
            """)

            existing = {row[1] for row in cursor.execute(
                'PRAGMA table_info(mcp_servers)')}
            for column, column_type in MCP_SERVER_ADDED_COLUMNS:
                if column not in existing:
                    cursor.execute(
                        f'ALTER TABLE mcp_servers ADD COLUMN {column} {column_type}')

            conn.commit()

    def add_server(self, user_id, name, transport, command=None, args=None,
                   env=None, url=None, headers=None, description=None,
                   is_builtin=False, is_enabled=True):
        """Returns the new server's id, or None if this user already has a
        server under that name - which is what makes re-seeding the built-in
        servers on every login a no-op. An unusable transport raises instead,
        so a bug is never mistaken for a duplicate."""
        if transport not in MCP_SERVER_TRANSPORTS:
            raise ValueError(f"Unknown MCP transport: {transport!r}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()
            try:
                cursor.execute("""
                INSERT INTO mcp_servers (id, user_id, name, transport, command, args,
                                         env, url, headers, description,
                                         is_builtin, is_enabled, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (id, user_id, name, transport, command,
                    json.dumps(args) if args is not None else None,
                    json.dumps(env) if env is not None else None,
                    url,
                    json.dumps(headers) if headers is not None else None,
                    description, int(is_builtin), int(is_enabled), created_at))
                conn.commit()
                return id
            except sqlite3.IntegrityError:
                return None

    def get_servers_by_user_id(self, user_id):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM mcp_servers WHERE user_id = ? ORDER BY created_at', (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_server_by_id(self, id):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mcp_servers WHERE id = ?', (id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_server_by_name(self, user_id, name):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM mcp_servers WHERE user_id = ? AND name = ?', (user_id, name))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_field(self, id, field):
        """Reads a single column off one server. `field` is checked against
        the column whitelist because it is interpolated into the query."""
        if field not in MCP_SERVER_COLUMNS:
            raise ValueError(f"Unknown mcp_servers field: {field}")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f'SELECT {field} FROM mcp_servers WHERE id = ?', (id,))
            row = cursor.fetchone()

        if row is None:
            return None
        if field in MCP_SERVER_JSON_COLUMNS:
            return json.loads(row[0]) if row[0] else None
        return row[0]

    def update_server(self, server_id, **fields):
        # Named `server_id`, not `id`: a caller passing id=... as a field must
        # land in **fields and be rejected by the whitelist, not collide with
        # this parameter and raise TypeError.
        unknown = set(fields) - MCP_SERVER_EDITABLE_COLUMNS
        if unknown:
            raise ValueError(f"Cannot update mcp_servers fields: {sorted(unknown)}")
        if not fields:
            raise ValueError("No new data provided for update.")
        if 'transport' in fields and fields['transport'] not in MCP_SERVER_TRANSPORTS:
            raise ValueError(f"Unknown MCP transport: {fields['transport']!r}")

        updates = []
        values = []
        for column, value in fields.items():
            updates.append(f"{column} = ?")
            if column in MCP_SERVER_JSON_COLUMNS and value is not None:
                value = json.dumps(value)
            elif column in ('is_builtin', 'is_enabled') and value is not None:
                value = int(value)
            values.append(value)
        values.append(server_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE mcp_servers SET {', '.join(updates)} WHERE id = ?", tuple(values))
            updated = cursor.rowcount
            conn.commit()
        return updated > 0

    def delete_server(self, id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM mcp_servers WHERE id = ?', (id,))
            deleted = cursor.rowcount
            conn.commit()
        return deleted > 0


class Secret_DB:
    """Encrypted secret values, kept out of the server rows so a connection
    only ever stores a reference to one."""

    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def _get_connection(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS secrets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    ciphertext TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE (user_id, name)
                )
            """)
            conn.commit()

    def set_secret(self, user_id, name, ciphertext):
        """Upsert, so rotating a token overwrites it instead of failing on the
        unique constraint."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO secrets (id, user_id, name, ciphertext, created_at, updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(user_id, name)
                DO UPDATE SET ciphertext = excluded.ciphertext,
                              updated_at = excluded.updated_at
    """, (str(uuid.uuid4()), user_id, name, ciphertext, now, now))
            conn.commit()

    def get_secret(self, user_id, name):
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM secrets WHERE user_id = ? AND name = ?', (user_id, name))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_names_by_user_id(self, user_id):
        """Names only - the ciphertext never leaves this class unless asked
        for by name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT name FROM secrets WHERE user_id = ? ORDER BY name', (user_id,))
            return [row[0] for row in cursor.fetchall()]

    def delete_secret(self, user_id, name):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM secrets WHERE user_id = ? AND name = ?', (user_id, name))
            deleted = cursor.rowcount
            conn.commit()
        return deleted > 0
