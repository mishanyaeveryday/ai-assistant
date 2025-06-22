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


class Subscription:
    def __init__(self, id, name, features, price, duration_days, is_active):
        self.id = id
        self.name = name
        self.features = features
        self.price = price
        self.duration_days = duration_days


class UserSubscription:
    def __init__(self, id, user_id, subscription_id, activated_at, expires_at, is_cancelled):
        self.id = id
        self.user_id = user_id
        self.subscription_id = subscription_id
        self.activated_at = activated_at
        self.expires_at = expires_at
        self.is_cancelled = is_cancelled


class Tool:
    def __init__(self, id, name, description):
        self.id = id
        self.name = name
        self.description = description


class SubscriptionTool:
    def __init__(self, id, subscription_id, tool_id, is_enabled):
        self.id = id
        self.subscription_id = subscription_id
        self.tool_id = tool_id
        self.is_enabled = is_enabled


class Chat:
    def __init__(self, id, title, user_id, created_at):
        self.id = id
        self.title = title
        self.user_id = user_id
        self.created_at = created_at


class MessageHistory:
    def __init__(self, id, user_input, assistant_output, chat_id, timestamp):
        self.id = id
        self.input = user_input
        self.output = assistant_output
        self.chat_id = chat_id
        self.timestamp = timestamp
