from tools.code_interpreter import CodeGenerator, DockerCodeInterpreter
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain import hub


from config.settings import GROQ_API_KEY, GROQ_MODEL, GENAI_API_KEY, GENAI_MODEL

from agent.mcp_client import MCPClient


class AIClient:
    def __init__(self, memory: ConversationBufferMemory, tools, model=GENAI_MODEL):
        self.memory = memory
        self.llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            api_key=GENAI_API_KEY
        )

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

    async def ask(self, user_input: str) -> str:
        result = await self.agent_executor.ainvoke({
            'input': user_input,
            'chat_history': self.memory.chat_memory.messages
        })
        return result['output']
