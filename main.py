from interface.cli import main
from db.database import Chat_DB, MessageHistory_DB

Chat_DB().create_table()
MessageHistory_DB().create_table()

main(user_id=None)
