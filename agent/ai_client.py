import ollama

response = ollama.chat(
    model='deepseek-r1:8b',
    messages=[
        {
            'role': 'user',
            # This is supposed to be a question from the User
            'content': 'Hello. Who you are?',
        }
    ]
)

print(response['message']['content'])
