from db.models import User, Subscription, UserSubscription, Tool, SubscriptionTool, Chat, MessageHistory
import sqlite3
import uuid
import json
from datetime import datetime, timedelta


class User_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
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
        conn.close()

    def add_user(self, username, email, password):
        hashed_password = User.hash_password(password)
        conn = self.connect()
        cursor = conn.cursor()
        id = str(uuid.uuid4())
        try:
            cursor.execute("""
            INSERT INTO users (id, username, email, password)
            VALUES (?,?,?)
""", (id, username, email, hashed_password))
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(
                "User with this username or email already exists.")
        finally:
            conn.close()

    def get_user_by_username(self, username):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM users WHERE username = ?', (username))
        result = cursor.fetchone()
        conn.close()
        if result:
            return User(*result)
        return None

    def get_user_by_id(self, user_id):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM users WHERE id = ?', (user_id))
        result = cursor.fetchone()
        conn.close()
        if result:
            return User(*result)
        return None

    def get_all_users(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users')
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [User(*row) for row in rows]
        return []


class Subscription_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
                       id TEXT PRIMARY KEY,
                       name TEXT UNIQUE NOT NULL,
                       tool_id TEXT,
                       price TEXT NOT NULL,
                       duration_days TEXT,
        )""")
        conn.commit()
        conn.close()

    def get_all_subscriptions(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM subscriptions')
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [Subscription(*row) for row in rows]
        return []

    def get_subscription_by_id(self, subscription_id):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM subscriptions WHERE id = ?', (subscription_id))
        result = cursor.fetchone()
        conn.close()
        if result:
            return Subscription(*result)
        return None

    def add_subscription(self, name, tool_id, price, duration_days=30):
        conn = self.connect()
        cursor = conn.cursor()
        id = str(uuid.uuid4())
        try:
            cursor.execute("""
                INSERT INTO subscriptions (id, name, tool_id, price, duration_days, is_active)
                VALUES (?,?,?)
""", (id, name, tool_id, price, duration_days, 0))
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(
                "Subscription with this name already exists.")
        finally:
            conn.close()


class UserSubscription_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_cancelled INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def add_user_subscription(self, user_id, subscription_id, duration_days=30):
        conn = self.connect()
        cursor = conn.cursor()

        id = str(uuid.uuid4())
        subscription_id = str(subscription_id)
        now = datetime.now()
        expires_at = now + timedelta(days=int(duration_days))

        cursor.execute("""
            INSERT INTO user_subscriptions (id, user_id, subscription_id, activated_at, expires_at, is_cancelled)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (
            id,
            user_id,
            subscription_id,
            now.isoformat(),
            expires_at.isoformat()
        ))

        conn.commit()
        conn.close()
        return id

    def get_user_subscriptions_by_user_id(self, user_id):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_subscriptions WHERE user_id = ?
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [UserSubscription(*row) for row in rows]
        return []

    def cancel_subscription(self, subscription_id):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_subscriptions
            SET is_cancelled = 1
            WHERE id = ?
        """, (subscription_id,))
        conn.commit()
        conn.close()


class Tool_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT
            )
        """)
        conn.commit()
        conn.close()

    def add_tool(self, name, description):
        conn = self.connect()
        cursor = conn.cursor()
        id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO tools (id, name, description)
            VALUES (?, ?, ?)
        """, (id, name, description))
        conn.commit()
        conn.close()

    def get_tool_by_id(self, id: str):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tools WHERE id = ?
        """, (id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return Tool(
                id=row[0], name=row[1], description=row[2]
            )
        return None

    def get_all_tools(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tools
        """)
        rows = cursor.fetchall()
        conn.close()

        return [
            Tool(
                id=row[0], name=row[1], description=row[2])
            for row in rows
        ]


class Chat_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
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
        conn.close()

    def get_all_chats(self, user_id=None):
        conn = self.connect()
        cursor = conn.cursor()

        if user_id is not None:
            cursor.execute('SELECT * FROM chats WHERE user_id = ?', (user_id,))
        else:
            cursor.execute('SELECT * FROM chats WHERE user_id IS NULL')

        rows = cursor.fetchall()
        conn.close()

        return [Chat(*row) for row in rows] if rows else []

    def get_chat_by_id(self, id):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM chats WHERE id = ?', (id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return Chat(*row)
        return None

    def add_chat(self, title=None, user_id=None):
        conn = self.connect()
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
        finally:
            conn.close()


class MessageHistory_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
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
        conn.close()

    def get_all_messages(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM messages_history')
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [MessageHistory(*row) for row in rows]
        return []

    def get_messages_from_chat(self, chat_id):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM messages_history WHERE chat_id = ? ORDER BY timestamp', (chat_id,))
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [MessageHistory(*row) for row in rows]
        return []

    def get_last_message(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM messages_history ORDER BY timestamp DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        if row:
            return MessageHistory(*row)
        return None

    def add_message(self, chat_id, user_input=None, assistant_output=None):
        conn = self.connect()
        cursor = conn.cursor()
        id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        assistant_output_str = json.dumps(assistant_output)
        try:
            cursor.execute("""
            INSERT INTO messages_history (id, input, output, chat_id, timestamp)
            VALUES (?,?,?,?,?)
""", (id, user_input, assistant_output_str, chat_id, timestamp))
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("Message with this ID already exists.")
        finally:
            conn.close()

    def edit_message(self, id, user_input, assistant_output):
        conn = self.connect()
        cursor = conn.cursor()
        updates = []
        values = []

        if user_input is not None:
            updates.append("input = ?")
            values.append(user_input)
        if assistant_output is not None:
            updates.append("output = ?")
            values.append(user_input)

        if not updates:
            raise ValueError("No new data provided for update.")

        values.append(id)
        query = f"""
        UPDATE messages_history
        SET {','.join(updates)}
        WHERE id = ? """

        cursor.execute(query, values)
        conn.commit()
        conn.close()
