# Launch applications, manage windows
from langchain.tools import tool
import re
import os
import tempfile
from pathlib import Path
import docker
from langchain_groq import ChatGroq
from pydantic import Field, BaseModel
from typing import Type
from langchain.tools import BaseTool
from langchain_core.messages import SystemMessage, HumanMessage
import subprocess

CODE_GENERATION_SYSTEM_PROMPT = """
You are an intelligent AI agent designed to generate accurate python code and you SHOULD to use tool generate_code
Here are your STRICT instructions:
- If the question does not require writing code, provide a clear and concise answer without generating any code.
- Whatever question is asked to you generate just the python code based on that and it's important that you just generate the code, no explanation of the code before or after.
- Think step by step how to solve the problem before you write the code.
- If the code involves doing system level tasks, it should have the code to identify the platform, the $HOME directory to make sure the code execution is successful.
- Code should be inside of the ```python ``` block.
- Make sure all the imports are always there to perform the task.
- At the end of the generated code, always include a line to run the generated function.
- The code should print output in a human-readable and understandable format.
- If you are generating charts, graphs or anything visual, convert them to image and save it to the /workspace location and return as well as print just the name of the image file without path.
"""


class CodeGeneratorInput(BaseModel):
    query: str = Field(
        description="A clear and detailed Python coding task in STR format. "
        "Describe what the program/function/class should do, "
        "expected inputs and outputs, and any specific requirements "
        "(e.g., use standard libraries only, add error handling, write tests). "
        "The description must be explicit enough so another developer could write the code directly.")


class CodeGenerator(BaseTool):
    name: str = "code-generator"
    description: str = "Useful when you need to generate python code"
    args_schema: Type[BaseModel] = CodeGeneratorInput
    llm: ChatGroq

    def _run(self, query):
        print('CODE GENERATOR TOOL')
        messages = [SystemMessage(content=CODE_GENERATION_SYSTEM_PROMPT),
                    HumanMessage(content=query)]
        response = self.llm.invoke(messages)
        print(response.content)
        code = response.content
        return code
        # self._get_code_group(response.content)

    def _get_code_group(self, llm_response: str) -> str | bool:
        code_match = re.search(r"```python\s*(.*?)```",
                               llm_response, re.DOTALL)
        if not code_match:
            return False
        return code_match.group(1).strip()


class CodeInterpreterInput(BaseModel):
    code: str = Field(
        description="A STR of valid Python code to be executed.")


class LocalCodeInterpreter(BaseTool):
    name: str = 'local-code-interpreter'
    description: str = "Use this tool to execute a given string of Python code in a local environment. The input MUST be valid Python code, so before using this tool you need to use code_generator tool."
    args_schema: Type[BaseModel] = CodeInterpreterInput

    def _run(self, code: str) -> str:
        clean_code = code.replace("```", "")
        my_path = 'files/interpreter.py'
        with open(my_path, "w") as f:
            f.write(clean_code)
        isCorrect = subprocess.run(
            ["python3", my_path])
        return isCorrect


class DockerCodeInterpreter(BaseTool):
    name: str = 'docker-code-interpreter'
    description: str = "Use this tool to execute a given string of Python code in a secure sandboxed environment. The input MUST be valid Python code, so before using this tool you need to use code_generator tool."
    args_schema: Type[BaseModel] = CodeInterpreterInput

    def _run(self, code: str) -> str:
        print('CODE INTERPRETER TOOL')

        # ИЗМЕНЕНИЕ: Создаем директорию, которая НЕ удалится автоматически
        # Имя папки будет уникальным, например /tmp/ai_assistant_sandbox_xyz123
        temp_dir = tempfile.mkdtemp(prefix="ai_assistant_sandbox_")
        host_dir = Path(temp_dir)
        script_path = host_dir / "main.py"
        script_path.write_text(code, encoding="utf-8")

        # Сообщаем пользователю, где искать файлы
        print(f"--- [Executor] Sandbox directory created at: {host_dir} ---")

        client = docker.from_env()
        try:
            container = client.containers.run(
                'code_interpreter:latest',
                command="python /workdir/main.py",
                volumes={str(host_dir.resolve()): {
                    'bind': '/workdir', 'mode': 'rw'}},
                remove=True,
                stderr=True,
                stdout=True
            )
            output = container.decode("utf-8")

            # После выполнения проверяем, какие файлы появились в папке
            created_files = [
                f.name for f in host_dir.iterdir() if f.name != 'main.py']
            if created_files:
                return f"Execution successful. Created files: {', '.join(created_files)}. Find them at {host_dir}"
            else:
                return f"Execution successful. Output:\n{output}"

        except Exception as e:
            return f"Failed running the container: {str(e)}"
