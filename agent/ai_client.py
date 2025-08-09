from langchain_groq import ChatGroq
from langchain import hub
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.memory import ConversationBufferMemory
from tools.docx_tool import create_docx
from tools.web_search import web_searching
from config.settings import GROQ_API_KEY


class AIClient:
    def __init__(self, memory: ConversationBufferMemory, model='llama3-70b-8192'):
        self.memory = memory
        self.llm = ChatGroq(
            model_name=model,
            temperature=0,
            api_key=GROQ_API_KEY
        )

        tools = [create_docx, web_searching]

        prompt = hub.pull("hwchase17/openai-functions-agent")

        agent = create_tool_calling_agent(
            llm=self.llm,
            tools=tools,
            prompt=prompt,
        )

        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            memory=self.memory,
            handle_parsing_errors=True,
        )

    def ask(self, user_input: str) -> str:
        return self.agent_executor.invoke({
            'input': user_input,
            'chat_history': self.memory.chat_memory.messages
        })
