from pathlib import Path
import re
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture
def files_dir(tmp_path):
    host_dir = tmp_path / "files"
    host_dir.mkdir(exist_ok=True)
    return host_dir


def test_run_docker_container(files_dir):
    code = '''with open("/app/hello.txt", "w", encoding="utf-8") as f:
    f.write("Hello, world!")'''

    from tools.code_interpreter import DockerCodeInterpreter
    interpreter = DockerCodeInterpreter()

    script_path = files_dir / "main.py"
    script_path.write_text(code, encoding="utf-8")

    container = interpreter.run_docker_container(files_dir)

    created_file = files_dir / "hello.txt"
    assert created_file.exists()
    assert created_file.read_text(encoding="utf-8") == "Hello, world!"

    assert "Execution successful" in container
    assert "hello.txt" in container


def test_run_1(files_dir):
    code = '''print("Hello World!")'''
    from tools.code_interpreter import DockerCodeInterpreter
    interpreter = DockerCodeInterpreter(host_dir=files_dir)
    result = interpreter._run(code)
    assert "Execution successful" in result


def test_run_2(files_dir):
    code = '''```python print("Hello World!")```'''
    from tools.code_interpreter import DockerCodeInterpreter
    interpreter = DockerCodeInterpreter(host_dir=files_dir)
    result = interpreter._run(code)
    assert "Failed running the container" in result
