import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import docker
from docker.errors import APIError, ContainerError, ImageNotFound
from mcp.server.fastmcp import FastMCP

try:
    from config.settings import DOCKER_CONTAINER, WORKSPACE_DIR
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from config.settings import DOCKER_CONTAINER, WORKSPACE_DIR

mcp = FastMCP("code-interpreter")

WORKSPACE = Path(WORKSPACE_DIR).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

_FENCE_RE = re.compile(r"^```(?:python)?\s*\n?|\n?```\s*$", re.MULTILINE)


def _strip_code_fence(code: str) -> str:
    return _FENCE_RE.sub("", code).strip()


@mcp.tool(description=(
    "Execute a snippet of Python code inside an isolated, disposable Docker sandbox. "
    "The code itself is never written to disk outside the sandbox and is deleted the moment "
    "execution finishes - nothing about it persists between calls. Anything printed by the code "
    "is returned as the tool output. If the code needs to keep a file after execution (a report, "
    "an image, generated data, etc.), have it write that file under /workspace inside the sandbox - "
    "that path is mounted to the user's persistent workspace and survives; everything written "
    "elsewhere (e.g. the current directory) is scratch space that is discarded on exit."
))
async def run_python_code(
    code: Annotated[str, "Valid, self-contained Python source code to execute."],
) -> str:
    if not DOCKER_CONTAINER:
        return "Error: DOCKER_CONTAINER is not configured, cannot run sandboxed code."

    clean_code = _strip_code_fence(code)
    if not clean_code:
        return "Error: no code was provided to execute."

    client = docker.from_env()

    with tempfile.TemporaryDirectory(prefix="code-interpreter-") as tmp_dir:
        sandbox_dir = Path(tmp_dir)
        (sandbox_dir / "main.py").write_text(clean_code, encoding="utf-8")

        try:
            output = client.containers.run(
                DOCKER_CONTAINER,
                command="python /sandbox/main.py",
                working_dir="/sandbox",
                volumes={
                    str(sandbox_dir): {"bind": "/sandbox", "mode": "rw"},
                    str(WORKSPACE): {"bind": "/workspace", "mode": "rw"},
                },
                remove=True,
                stderr=True,
                stdout=True,
            )
            return output.decode("utf-8") or "Execution finished with no output."
        except ContainerError as e:
            stderr = e.stderr.decode("utf-8") if isinstance(e.stderr, bytes) else str(e.stderr)
            return f"Execution failed (exit {e.exit_status}):\n{stderr}"
        except (ImageNotFound, APIError) as e:
            return f"Docker error: {e}"
        except Exception as e:
            return f"Sandbox execution failed: {e}"
    # sandbox_dir, including main.py, is removed automatically here - the code never outlives this call


if __name__ == "__main__":
    mcp.run(transport='stdio')