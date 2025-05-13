# Console interface
import sys
import time
import threading
from agent.ai_client import ai_question

history = []


def smooth_print(text, delay=0.009):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)


def async_print(text, delay=0.009):
    thread = threading.Thread(target=smooth_print, args=(text, delay))
    thread.start()


print("🤖 AI Assistant started (type 'exit' to quit)\n")
while True:
    user_input = input("You: ")
    if user_input.lower() in ("exit", "quit"):
        break
    reply = ai_question(user_input, history)
    async_print("Assistant: " + reply + "\n")
    time.sleep(1)
