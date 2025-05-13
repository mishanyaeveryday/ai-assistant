import ollama


def ai_question(user_input, history=None):
    if history is None:
        history = []

    history.append({'role': 'user', 'content': user_input})
    response = ollama.chat(
        model='deepseek-r1:8b',
        messages=history
    )

    assistant_reply = response['message']['content']

    history.append({'role': 'assistant', 'content': assistant_reply})

    return assistant_reply
