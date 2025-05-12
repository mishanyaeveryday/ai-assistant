import sqlite3
import uuid
from datetime import datetime, timedelta
from models import User, Subscription, UserSubscription, Command, SubscriptionCommand


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
                       features TEXT,
                       price TEXT NOT NULL,
                       duration_days TEXT,
                       is_active INTEGER
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

    def add_subscription(self, name, features, price, duration_days=30):
        conn = self.connect()
        cursor = conn.cursor()
        id = str(uuid.uuid4())
        try:
            cursor.execute("""
                INSERT INTO subscriptions (id, name, features, price, duration_days, is_active)
                VALUES (?,?,?)
""", (id, name, features, price, duration_days, 0))
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


class Command_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                command_type TEXT,
                status TEXT
            )
        """)
        conn.commit()
        conn.close()

    def add_command(self, user_id: str, command_type: str, status: str = "waiting", result: str = None):
        conn = self.connect()
        cursor = conn.cursor()
        id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO commands (id, user_id, command_type, status, result)
            VALUES (?, ?, ?, ?, ?)
        """, (id, user_id, command_type, status, result))
        conn.commit()
        conn.close()

    def update_command_status(self, id: str, status: str):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE commands
            SET status = ?
            WHERE id = ?
        """, (status, id))
        conn.commit()
        conn.close()

    def update_command_result(self, id: str, result: str):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE commands
            SET result = ?
            WHERE id = ?
        """, (result, id))
        conn.commit()
        conn.close()

    def get_command(self, id: str):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM commands WHERE id = ?
        """, (id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return Command(
                id=row[0], user_id=row[1], command_type=row[2], status=row[3], result=row[4]
            )
        return None

    def get_all_commands(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM commands
        """)
        rows = cursor.fetchall()
        conn.close()

        return [
            Command(
                id=row[0], user_id=row[1], command_type=row[2], status=row[3])
            for row in rows
        ]


class SubscriptionCommand_DB:
    def __init__(self, db_name='ai-assistent.sqlite3'):
        self.db_name = db_name

    def connect(self):
        return sqlite3.connect(self.db_name)

    def create_table(self):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscription_commands (
                id TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL,
                command_id TEXT NOT NULL,
                is_enabled INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def add_subscription_command(self, subscription_id: str, command_id: str, is_enabled: bool = False):
        conn = self.connect()
        cursor = conn.cursor()
        id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO subscription_commands (id, subscription_id, command_id, is_enabled) VALUES (?, ?, ?, ?, ?)
        """, (id, subscription_id, command_id, int(is_enabled)))
        conn.commit()
        conn.close()

    def get_commands_by_subscription_id(self, subscription_id):
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM subscription_commands WHERE subscription_id = ? AND is_enabled = 1 
        """, (subscription_id))
        rows = cursor.fetchall()
        conn.close()

        return [
            SubscriptionCommand(
                id=row[0], subscription_id=row[1], command_id=row[2], is_enabled=bool(row[3]))
            for row in rows
        ]
