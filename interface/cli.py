# Console interface
import sys
import time
import threading
from agent.ai_client import AIClient
from db.database import Chat_DB, MessageHistory_DB

history = []


def smooth_print(text, delay=0.009):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)


def async_print(text, delay=0.009):
    thread = threading.Thread(target=smooth_print, args=(text, delay))
    thread.start()


def ai_assistant(chat_id):
    agent = AIClient()
    print("🤖 AI Assistant started (type 'exit' to quit)\n")
    msg_db = MessageHistory_DB()
    message_history = msg_db.get_messages_from_chat(chat_id)
    history = []
    for msg in message_history:
        if msg.input:
            history.append({'role': 'user', 'content': msg.input})
        if msg.output:
            history.append({'role': 'assistant', 'content': msg.output})
    agent.set_history(history=history)

    while True:
        user_input = input("You: ")
        if user_input.lower() in ("exit", "quit"):
            break
        reply = agent.ask(user_input)
        msg_db.add_message(chat_id, user_input=user_input,
                           assistant_output=reply)
        for char in reply:
            print(char, end='', flush=True)
            time.sleep(0.01)
        print("\n")


def open_chat(user_id, chat_id):
    chat_db = Chat_DB()
    selected_chat = chat_db.get_chat_by_id(chat_id)
    print(
        f"Selected chat ID: {selected_chat.id}, Created at: {selected_chat.created_at}")
    ai_assistant(selected_chat.id)


def main(user_id=None):
    chat_db = Chat_DB()

    while True:
        chats = chat_db.get_all_chats(user_id)

        chats_dict = {}
        print("\nMenu:")
        print("1. Create new chat")

        if not chats:
            print("   No chats yet.")
        else:
            for index, chat in enumerate(chats, start=2):
                chats_dict[index] = chat.id
                print(f"{index}. {chat.title} (created at {chat.created_at})")
        print("0. Exit")
        try:
            option = int(input("Select option: "))
        except ValueError:
            print("Please enter a number.")
            continue

        match option:
            case 1:
                chat_title = str(input('Enter title of chat: '))
                chat_db.add_chat(user_id=user_id, title=chat_title)
                print("Chat created!")
            case 0:
                break
            case _ if option in chats_dict:
                selected_chat = chat_db.get_chat_by_id(chats_dict[option])
                open_chat(user_id, selected_chat.id)
            case _:
                print("Invalid option.")
