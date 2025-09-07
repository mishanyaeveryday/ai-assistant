from langchain_groq import ChatGroq
from langchain import hub
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.memory import ConversationBufferMemory
from tools.web_search import web_searching_tool
from tools.code_interpreter import CodeGenerator, DockerCodeInterpreter
from config.settings import GROQ_API_KEY, GROQ_MODEL, GENAI_API_KEY, GENAI_MODEL
from langchain_google_genai import ChatGoogleGenerativeAI


class AIClient:
    def __init__(self, memory: ConversationBufferMemory, model=GENAI_MODEL):
        self.memory = memory
        self.llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            api_key=GENAI_API_KEY
        )

        code_generator_tool = CodeGenerator(llm=self.llm)
        docker_code_interpreter_tool = DockerCodeInterpreter()
        tools = [web_searching_tool, code_generator_tool,
                 docker_code_interpreter_tool]

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

# GROQ
# class AIClient:
#     def __init__(self, memory: ConversationBufferMemory, model=GROQ_MODEL):
#         self.memory = memory
#         self.llm = ChatGroq(
#             model=model,
#             temperature=0,
#             api_key=GROQ_API_KEY
#         )

#         code_generator_tool = CodeGenerator(llm=self.llm)
#         docker_code_interpreter_tool = DockerCodeInterpreter()
#         tools = [web_searching_tool, code_generator_tool,
#                  docker_code_interpreter_tool]

#         prompt = hub.pull("hwchase17/openai-functions-agent")

#         agent = create_tool_calling_agent(
#             llm=self.llm,
#             tools=tools,
#             prompt=prompt,

#         )

#         self.agent_executor = AgentExecutor(
#             agent=agent,
#             tools=tools,
#             verbose=True,
#             memory=self.memory,
#             handle_parsing_errors=True,
#         )

#     def ask(self, user_input: str) -> str:
#         return self.agent_executor.invoke({
#             'input': user_input,
#             'chat_history': self.memory.chat_memory.messages
#         })
