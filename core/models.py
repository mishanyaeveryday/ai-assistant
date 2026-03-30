

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
