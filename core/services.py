import bcrypt
from db.database import User_DB
from core.models import User


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
