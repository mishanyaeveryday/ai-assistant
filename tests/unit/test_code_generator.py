from unittest.mock import MagicMock
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def test_get_code_group_1():
    from tools.code_interpreter import CodeGenerator
    mock_llm = MagicMock()
    generator = CodeGenerator(llm=mock_llm)

    raw_code = "```python\nprint('Hello World')\n```"
    extracted_code = generator._get_code_group(raw_code)
    assert extracted_code == "print('Hello World')"


def test_get_code_group_2():
    from tools.code_interpreter import CodeGenerator
    mock_llm = MagicMock()
    generator = CodeGenerator(llm=mock_llm)

    raw_code = "```python\ndef main():\nprint('Hello World')\n```"
    extracted_code = generator._get_code_group(raw_code)
    assert extracted_code == "def main():\nprint('Hello World')"


def test_get_code_group_3():
    from tools.code_interpreter import CodeGenerator
    mock_llm = MagicMock()
    generator = CodeGenerator(llm=mock_llm)

    raw_code = "```python\nprint('Hello World')\n```\n```python\nprint('Hello World')\n```"
    extracted_code = generator._get_code_group(raw_code)
    assert extracted_code == "print('Hello World')"


def test_get_code_group_empty_1():
    from tools.code_interpreter import CodeGenerator
    mock_llm = MagicMock()
    generator = CodeGenerator(llm=mock_llm)

    raw_code = ""
    extracted_code = generator._get_code_group(raw_code)
    assert extracted_code == False


def test_get_code_group_empty_2():
    from tools.code_interpreter import CodeGenerator
    mock_llm = MagicMock()
    generator = CodeGenerator(llm=mock_llm)

    raw_code = "```python ```"
    extracted_code = generator._get_code_group(raw_code)
    assert extracted_code == False


def test_get_code_group_empty_3():
    from tools.code_interpreter import CodeGenerator
    mock_llm = MagicMock()
    generator = CodeGenerator(llm=mock_llm)

    raw_code = "```python    ```"
    extracted_code = generator._get_code_group(raw_code)
    assert extracted_code == False


def test_run_code_generator():
    from tools.code_interpreter import CodeGenerator
    llm = MagicMock()

    query = llm.stream.return_value = [
        MagicMock(content='```python\n'),
        MagicMock(content="print('Hello World!')"),
        MagicMock(content="\n```")
    ]
    generator = CodeGenerator(llm=llm)

    query = "Write Python code 'Hello World!'"

    result = generator._run(query=query)

    assert result == "print('Hello World!')"

    assert llm.stream.called
