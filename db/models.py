import sqlite3
import uuid
from datetime import datetime
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
        def hash_password(pasword):
            return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        @staticmethod
        def check_password(stored_password, provided_password):
            return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))


class User_DB:
    def __init__(self, db_name='users.db'):
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
                       language TEXT,
                       history_enabled INTEGER,
                       is_active INTEGER
        )""")
        conn.commit()
        conn.close()

        def add_user(self, username, email, password):
            hashed_password = User.hash_password(password)
            conn = self.connect
            cursor = conn.cursor()
            try:
                cursor.execute("""
                INSERT INTO users (username, email, password)
                VALUES (?,?,?)
"""), (username, email, hashed_password)
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(
                    "User with this username or email already exists.")
            finally:
                conn.close()

        def get_user_by_username(self, username):
            conn = self.connect
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM users WHERE username = ?', (username))
            result = cursor.fetchone()
            conn.close()
            if result:
                return User(*result)
            return None

        def get_user_by_id(self, user_id):
            conn = self.connect
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM users WHERE id = ?', (user_id))
            result = cursor.fetchone()
            conn.close()
            if result:
                return User(*result)
            return None
