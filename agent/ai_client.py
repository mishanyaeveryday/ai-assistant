from langchain.agents import initialize_agent, AgentType
from langchain_community.chat_models import ChatOllama
from tools.docx_tool import create_docx


class AIClient:
    def __init__(self, model='deepseek-r1:8b'):
        self.history = []
        self.agent = initialize_agent(
            llm=ChatOllama(model=model),
            tools=[create_docx],
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            handle_parsing_errors=True
        )

    def ask(self, user_input: str) -> str:
        return self.agent.invoke(user_input)

    def set_history(self, history):
        self.history = history

    def reset_history(self):
        self.history = []
