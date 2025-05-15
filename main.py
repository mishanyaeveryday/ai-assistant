from interface.cli import main
from db.database import Chat_DB, MessageHistory_DB

# ✅ Создание таблиц, если они не существуют
Chat_DB().create_table()
MessageHistory_DB().create_table()

# Запуск основного меню
main(user_id=None)
