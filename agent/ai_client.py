from langchain_groq import ChatGroq
from langchain.agents import initialize_agent, AgentType
from tools.docx_tool import create_docx
from tools.web_search import web_searching
from config.settings import GROQ_API_KEY


class AIClient:
    def __init__(self, model='llama3-70b-8192'):
        self.history = []
        self.llm = ChatGroq(
            model_name=model,
            temperature=0,
            api_key=GROQ_API_KEY
        )
        self.agent = initialize_agent(
            llm=self.llm,
            tools=[create_docx, web_searching],
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            handle_parsing_errors=True,
        )

    def ask(self, user_input: str) -> str:
        return self.agent.invoke(user_input)

    def set_history(self, history):
        self.history = history

    def reset_history(self):
        self.history = []
