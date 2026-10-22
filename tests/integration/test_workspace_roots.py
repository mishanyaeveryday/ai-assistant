"""The chat's workspace reaches the real built-in servers as an MCP root.

Starts the filesystem and terminal servers as the app does, over stdio, so
the path makes the whole trip: file URI out, decoded path back.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from agent.mcp_client import ConnectionSpec, MCPClient  # noqa: E402

FILESYSTEM = ConnectionSpec(id="fs", name="filesystem", transport="stdio",
                            args=[str(ROOT / "mcp_tools/filesystem_command/server.py")])
TERMINAL = ConnectionSpec(id="term", name="terminal", transport="stdio",
                          args=[str(ROOT / "mcp_tools/terminal_command/server.py")])
# Only listed, never called: no Docker run, no model request.
CODE = ConnectionSpec(id="code", name="code", transport="stdio",
                      args=[str(ROOT / "mcp_tools/code_interpreter/server.py")])
SCREENSHOT = ConnectionSpec(id="shot", name="screenshot", transport="stdio",
                            args=[str(ROOT / "mcp_tools/screenshot_command/server.py")])


def _text(result) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content)


@pytest.fixture
def workspace(tmp_path):
    # Spaces and Cyrillic are percent-encoded in the root's URI.
    folder = tmp_path / "Документы" / "my folder"
    folder.mkdir(parents=True)
    return folder


def run(scenario):
    async def main():
        async with MCPClient() as client:
            return await scenario(client)
    return asyncio.run(main())


def test_tools_work_in_the_chat_folder(workspace):
    async def scenario(client):
        await client.set_workspace(str(workspace))
        await client.call_tool(FILESYSTEM, "write_file", {"path": "note.md", "content": "hi"})
        listing = _text(await client.call_tool(FILESYSTEM, "list_dir", {}))
        pwd = _text(await client.call_tool(TERMINAL, "terminal_command", {"command": "pwd"}))
        return listing, pwd

    listing, pwd = run(scenario)

    assert (workspace / "note.md").read_text() == "hi"
    assert listing == "note.md"
    assert Path(pwd.strip()).resolve() == workspace.resolve()


def test_switching_chats_moves_the_running_servers(workspace, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "x.txt").write_text("")

    async def scenario(client):
        await client.set_workspace(str(workspace))
        await client.call_tool(FILESYSTEM, "list_dir", {})
        await client.set_workspace(str(other))
        return _text(await client.call_tool(FILESYSTEM, "list_dir", {}))

    assert run(scenario) == "x.txt"


def test_absolute_paths_still_reach_other_folders(workspace, tmp_path):
    target = tmp_path / "elsewhere.txt"

    async def scenario(client):
        await client.set_workspace(str(workspace))
        await client.call_tool(FILESYSTEM, "write_file",
                               {"path": str(target), "content": "abs"})

    run(scenario)

    assert target.read_text() == "abs"
    assert os.listdir(workspace) == []


def test_a_deleted_folder_is_an_error_not_a_new_folder(tmp_path):
    gone = tmp_path / "gone"

    async def scenario(client):
        await client.set_workspace(str(gone))
        return await client.call_tool(FILESYSTEM, "write_file",
                                      {"path": "note.md", "content": "hi"})

    result = run(scenario)

    assert result.isError
    assert "no longer exists" in _text(result)
    assert not gone.exists()


def test_tool_schemas_do_not_show_the_context():
    async def scenario(client):
        tools = []
        for spec in (FILESYSTEM, TERMINAL, CODE, SCREENSHOT):
            tools += await client.list_tools(spec)
        return tools

    tools = run(scenario)
    assert {"run_python_code", "read_image"} <= {t.name for t in tools}
    for tool in tools:
        assert "ctx" not in tool.inputSchema.get("properties", {}), tool.name
