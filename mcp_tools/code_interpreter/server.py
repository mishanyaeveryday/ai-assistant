import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Annotated

import docker
from docker.errors import APIError, ContainerError, ImageNotFound
from mcp.server.fastmcp import Context, FastMCP

try:
    from config.settings import DOCKER_CONTAINER
    from mcp_tools.workspace import resolve_workspace
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from config.settings import DOCKER_CONTAINER
    from mcp_tools.workspace import resolve_workspace

mcp = FastMCP("code-interpreter")

_FENCE_RE = re.compile(r"^```(?:python)?\s*\n?|\n?```\s*$", re.MULTILINE)
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}
# A chat's workspace can be a real project, and walking all of it (its
# dependencies included) after every run would be slow. Charts land near the
# top of the workspace anyway.
_IMAGE_SCAN_DEPTH = 3
_SKIPPED_DIRS = {"node_modules", "__pycache__", "venv"}


def _strip_code_fence(code: str) -> str:
    return _FENCE_RE.sub("", code).strip()


def _new_images(workspace: Path, since: float) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(workspace):
        if len(Path(dirpath).relative_to(workspace).parts) >= _IMAGE_SCAN_DEPTH:
            dirnames[:] = []
        else:
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d not in _SKIPPED_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in _IMAGE_EXTS and p.stat().st_mtime >= since:
                found.append(p)
    return found


def _append_generated_image_markers(text: str, since: float, workspace: Path) -> str:
    """Tag any image file written to the workspace during this run so the
    caller can surface it (e.g. render a generated chart in the chat UI)."""
    new_images = _new_images(workspace, since)
    if not new_images:
        return text
    markers = "\n".join(f"[GENERATED_IMAGE:{p.resolve()}]" for p in new_images)
    return f"{text}\n{markers}"


@mcp.tool(description=(
    "Execute a snippet of Python code inside an isolated, disposable Docker sandbox. "
    "The code itself is never written to disk outside the sandbox and is deleted the moment "
    "execution finishes - nothing about it persists between calls. Anything printed by the code "
    "is returned as the tool output. If the code needs to keep a file after execution (a report, "
    "an image, generated data, etc.), have it write that file under /workspace inside the sandbox - "
    "that path is mounted to the chat's workspace folder on the user's machine and survives; "
    "everything written elsewhere (e.g. the current directory) is scratch space that is discarded "
    "on exit. /workspace is the only folder of the user's machine the sandbox can reach. "
    "Whenever the task involves a chart, plot, graph, diagram, or any other visual output, ALWAYS "
    "generate it as an actual image file (e.g. matplotlib's savefig(...)) saved under /workspace - "
    "never only print a textual description or ASCII rendering instead. Any image file saved this "
    "way is automatically detected and shown to the user as a visual report in the chat, so do not "
    "try to embed, encode, or re-describe the image yourself; just confirm briefly in your reply "
    "that the chart/image was created."
))
async def run_python_code(
    code: Annotated[str, "Valid, self-contained Python source code to execute."],
    ctx: Context = None,
) -> str:
    if not DOCKER_CONTAINER:
        return "Error: DOCKER_CONTAINER is not configured, cannot run sandboxed code."

    clean_code = _strip_code_fence(code)
    if not clean_code:
        return "Error: no code was provided to execute."

    workspace = await resolve_workspace(ctx)
    client = docker.from_env()
    start_time = time.time()

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
                    str(workspace): {"bind": "/workspace", "mode": "rw"},
                },
                remove=True,
                stderr=True,
                stdout=True,
            )
            text = output.decode(
                "utf-8") or "Execution finished with no output."
            return _append_generated_image_markers(text, start_time, workspace)
        except ContainerError as e:
            stderr = e.stderr.decode(
                "utf-8") if isinstance(e.stderr, bytes) else str(e.stderr)
            text = f"Execution failed (exit {e.exit_status}):\n{stderr}"
            return _append_generated_image_markers(text, start_time, workspace)
        except (ImageNotFound, APIError) as e:
            return f"Docker error: {e}"
        except Exception as e:
            return f"Sandbox execution failed: {e}"
    # sandbox_dir, including main.py, is removed automatically here - the code never outlives this call


if __name__ == "__main__":
    mcp.run(transport='stdio')
