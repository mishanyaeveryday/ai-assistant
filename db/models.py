import sqlite3
import uuid
from datetime import datetime, timedelta
import bcrypt


class User:
    def __init__(self, id, username, email, password, type_of_suscription,
                 os_type, created_at, last_active, language, history_enabled, is_active):
        self.id = id
        self.username = username
        self.email = email
        self.password = password
        self.type_of_subscription = type_of_suscription
        self.os_type = os_type
        self.created_at = created_at
        self.last_active = last_active
        self.language = language
        self.history_enabled = history_enabled
        self.is_active = is_active

    @staticmethod
    def hash_password(password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    @staticmethod
    def check_password(stored_password, provided_password):
        return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))


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


class Subscription:
    def __init__(self, id, name, features, price, duration_days, is_active):
        self.id = id
        self.name = name
        self.features = features
        self.price = price
        self.duration_days = duration_days
        self.is_active = is_active


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


class UserSubscription:
    def __init__(self, id, user_id, subscription_id, activated_at, expires_at, is_cancelled):
        self.id = id
        self.user_id = user_id
        self.subscription_id = subscription_id
        self.activated_at = activated_at
        self.expires_at = expires_at
        self.is_cancelled = is_cancelled


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
