from core.models import User, Chat, MessageHistory
import sqlite3
import uuid
from datetime import datetime, timedelta


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
