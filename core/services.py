import bcrypt
from core.models import User, Chat, MessageHistory
from db.database import User_DB, Chat_DB, MessageHistory_DB
from langchain.memory import ConversationSummaryBufferMemory
from langchain_groq import ChatGroq
from config.settings import GROQ_API_KEY, GROQ_MODEL, GENAI_API_KEY, GENAI_MODEL
from langchain_google_genai import ChatGoogleGenerativeAI


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


class MessageService:
    def __init__(self, message_db: MessageHistory_DB):
        self.message_db = message_db

    def get_messages_from_chat(self, chat_id):
        message_rows = self.message_db.get_messages_by_chat_id(chat_id=chat_id)

        if not message_rows:
            return []

        return [MessageHistory.from_db_row(row) for row in message_rows]


class AIClientService():
    def __init__(self, message_db: MessageHistory_DB, model=GENAI_MODEL):
        self.model = model
        self.message_db = message_db

        self.llm_for_summarization = ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            api_key=GENAI_API_KEY
        )

    def record_input(self, chat_id, input):
        id = self.message_db.add_input(chat_id=chat_id, user_input=input)
        return id

    def record_output(self, id, chat_id, output):
        self.message_db.add_output(
            message_history_id=id, chat_id=chat_id, assistant_output=output)

    def record_conversation(self, chat_id, input, output):
        self.message_db.add_input_and_output(
            chat_id=chat_id, user_input=input, assistant_output=output)

    def load_memory_for_chat(self, chat_id):
        message_history = self.message_db.get_messages_by_chat_id(
            chat_id=chat_id)

        memory = ConversationSummaryBufferMemory(
            llm=self.llm_for_summarization,
            max_token_limit=2000,
            memory_key="chat_history",
            return_messages=True
        )

        for msg in message_history:
            user_message = msg.get('input')
            ai_message = msg.get('output')

            if user_message:
                memory.chat_memory.add_user_message(user_message)

            if ai_message:
                memory.chat_memory.add_ai_message(ai_message)

        return memory
