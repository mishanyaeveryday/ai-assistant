import ollama


def ai_question(user_input, history):
    if history is None:
        history = []

    temp_history = history + [{'role': 'user', 'content': user_input}]

    response = ollama.chat(
        model='deepseek-r1:8b',
        messages=temp_history
    )

    return response['message']['content']
