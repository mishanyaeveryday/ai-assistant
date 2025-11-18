# Launch applications, manage windows
from langchain.tools import tool
import re
import os
import tempfile
from pathlib import Path
import docker
# from langchain_google_genai.chat_models import ChatGoogleGenerativeAI
from config.settings import GENAI_MODEL, DOCKER_CONTAINER
from typing import Optional
from pydantic import Field, BaseModel
from typing import Type

CODE_GENERATION_SYSTEM_PROMPT = """
You are an intelligent AI agent designed to generate accurate python3 code and you SHOULD to use tool generate_code
Here are your STRICT instructions:
- Write Python code that runs inside a Linux Docker container!
- Do not use Windows-specific libraries
- If the question does not require writing code, provide a clear and concise answer without generating any code.
- Whatever question is asked to you generate just the python code based on that and it's important that you just generate the code, no explanation of the code before or after.
- Think step by step how to solve the problem before you write the code.
- If the code involves doing system level tasks, it should have the code to identify the platform, the $HOME directory to make sure the code execution is successful.
- Code should be inside of the ```python ``` block.
- Make sure all the imports are always there to perform the task.
- At the end of the generated code, always include a line to run the generated function.
- The code should print output in a human-readable and understandable format.
- For any file you create (Word, text, CSV, images, etc.), always save it inside the /app directory.
- Prepend /app/ to the filename to ensure it is saved in the correct location accessible from the host.
- If you are generating charts, graphs or anything visual, convert them to image and save it to the /app location and return as well as print just the name of the image file without path.
"""


class CodeGeneratorInput(BaseModel):
    query: str = Field(
        description="A clear and detailed Python coding task "
        "Describe what the program/function/class should do, "
        "expected inputs and outputs, and any specific requirements "
        "(e.g., use standard libraries and python-docx, psutil, ipython, pandas, numpy, matplotlib, plotly, add error handling, write tests). "
        "The description must be explicit enough so another developer could write the code directly.")


class CodeGenerator:
    name: str = "code-generator"
    description: str = "Useful when you need to generate python code"
    args_schema: Type[BaseModel] = CodeGeneratorInput
    llm: Optional[ChatGoogleGenerativeAI] = None

    def __init__(self, llm: ChatGoogleGenerativeAI = None):
        if llm is None:
            self.llm = llm or ChatGoogleGenerativeAI(model=GENAI_MODEL)

    def run(self, query):
        print('CODE GENERATOR TOOL')
        messages = [SystemMessage(CODE_GENERATION_SYSTEM_PROMPT),
                    HumanMessage(query)]
        # response = self.llm.invoke(messages)
        response = self.llm.stream(messages)
        full_response = "".join([chunk.content for chunk in response])
        code = self._get_code_group(full_response)
        return code

    def _get_code_group(self, raw_code: str) -> str | bool:
        text = raw_code.strip()

        first_point = re.search(
            r"^```(?:python)?", text, flags=re.MULTILINE)
        second_point = re.search(r"```$", text, flags=re.MULTILINE)

        if first_point and second_point and first_point.end() < second_point.start():
            code = text[first_point.end():second_point.start()]
        else:
            code = text

        code = re.sub(r"<.*?>", "", code)
        code = code.strip()
        return code if code else False


class CodeInterpreterInput(BaseModel):
    code: str = Field(
        description="A STR of valid Python code to be executed.")


# class LocalCodeInterpreter(BaseTool):
#     name: str = 'local-code-interpreter'
#     description: str = "Use this tool for SAFETY proccess to execute a given string of Python code in a local environment. The input MUST be valid Python code, so before using this tool you need to use code_generator tool."
#     args_schema: Type[BaseModel] = CodeInterpreterInput

#     def _run(self, code: str) -> str:
#         clean_code = code.replace("```", "")
#         my_path = 'files/interpreter.py'
#         with open(my_path, "w") as f:
#             f.write(clean_code)
#         isCorrect = subprocess.run(
#             ["python3", my_path])
#         return isCorrect


class DockerCodeInterpreter:
    name: str = 'docker-code-interpreter'
    description: str = "Use this tool to execute a given string of Python code in a secure sandboxed environment. The input MUST be valid Python code, so before using this tool you need to use code_generator tool."
    args_schema: Type[BaseModel] = CodeInterpreterInput
    host_dir: Path = Field(default_factory=lambda: Path(
        __file__).resolve().parent / "files")

    def __init__(self, host_dir: Path | None = None):
        self.host_dir = host_dir or (Path(__file__).resolve().parent / "files")
        self.host_dir.mkdir(exist_ok=True)

    def run(self, code: str) -> str:
        print('CODE INTERPRETER TOOL')

        script_path = self.host_dir / "main.py"
        script_path.write_text(code, encoding="utf-8")

        print(
            f"--- [Executor] Sandbox directory created at: {self.host_dir} ---")

        return self.run_docker_container(self.host_dir)

    def run_docker_container(self, dir):
        client = docker.from_env()
        try:
            container = client.containers.run(
                DOCKER_CONTAINER,
                command="python /app/main.py",
                volumes={str(dir.resolve()): {
                    'bind': '/app', 'mode': 'rw'}},
                remove=True,
                stderr=True,
                stdout=True
            )
            output = container.decode("utf-8")

            created_files = [
                f.name for f in dir.iterdir() if f.name != 'main.py']
            if created_files:
                return f"Execution successful. Created files: {', '.join(created_files)}. Find them at {dir}"
            else:
                return f"Execution successful. Output:\n{output}"

        except Exception as e:
            return f"Failed running the container: {str(e)}"
