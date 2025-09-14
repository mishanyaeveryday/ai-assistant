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
    host_dir = tmp_path / 'files'
    host_dir.mkdir(exist_ok=True)
    return host_dir


@patch("tools.code_interpreter.docker.from_env")
def test_run_docker_container_mock_1(mock_docker, files_dir):
    mock_client = MagicMock()

    mock_docker.return_value = mock_client
    mock_client.containers.run.return_value = b"Test output"

    from tools.code_interpreter import DockerCodeInterpreter

    interpreter = DockerCodeInterpreter()

    result = interpreter.run_docker_container(files_dir)

    assert "Execution successful" in result
    mock_client.containers.run.assert_called_once()


@patch("tools.code_interpreter.docker.from_env")
def test_run_docker_container_mock_2(mock_docker, files_dir):
    mock_client = MagicMock()

    mock_docker.return_value = mock_client
    mock_client.containers.run.side_effect = Exception("Container failed")

    host_dir = files_dir

    from tools.code_interpreter import DockerCodeInterpreter

    interpreter = DockerCodeInterpreter(host_dir=host_dir)

    result = interpreter.run_docker_container(host_dir)

    assert "Failed running the container: " in result
    mock_client.containers.run.assert_called_once()
