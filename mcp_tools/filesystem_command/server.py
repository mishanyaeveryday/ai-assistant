import os
import sys
from pathlib import Path
from typing import Annotated
from mcp.server.fastmcp import FastMCP

try:
    from config.settings import WORKSPACE_DIR
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from config.settings import WORKSPACE_DIR

mcp = FastMCP("filesystem")

WORKSPACE = Path(WORKSPACE_DIR).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _resolve(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    return p


@mcp.tool()
async def read_file(path: Annotated[str, "Path of the file to read"]) -> str:
    '''Read and return the full text content of an existing file. Use this before editing a file to see its current content.'''
    return _resolve(path).read_text(encoding="utf-8")


@mcp.tool()
async def write_file(
    path: Annotated[str, "Path of the file to create or overwrite"],
    content: Annotated[str, "Full content to write into the file"],
) -> str:
    '''Create a new file or completely overwrite an existing file with the given content. Any existing content is lost — use append_file if you only want to add to the end, or delete_text to remove part of the content.'''
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


@mcp.tool()
async def append_file(
    path: Annotated[str, "Path of the file to append to"],
    content: Annotated[str, "Content to add to the end of the file"],
) -> str:
    '''Add content to the end of an existing file without touching what's already there. Creates the file if it does not exist yet.'''
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(content)
    return f"Appended {len(content)} bytes to {path}"


@mcp.tool()
async def delete_text(
    path: Annotated[str, "Path of the file to edit"],
    text: Annotated[str, "Exact text snippet to remove; must match the file content exactly, including whitespace"],
) -> str:
    '''Remove every occurrence of an exact text snippet from a file, keeping the rest of the content. Read the file first to get the exact text to match.'''
    p = _resolve(path)
    original = p.read_text(encoding="utf-8")
    updated, count = original.replace(text, ""), original.count(text)
    if count == 0:
        return f"Text not found in {path}, nothing changed"
    p.write_text(updated, encoding="utf-8")
    return f"Removed {count} occurrence(s) from {path}"


@mcp.tool()
async def delete_file(path: Annotated[str, "Path of the file to delete"]) -> str:
    '''Permanently delete a single file. Use list_dir first if unsure the file exists.'''
    _resolve(path).unlink()
    return f"Deleted {path}"


@mcp.tool()
async def list_dir(path: Annotated[str, "Directory path to list, defaults to the current directory"] = ".") -> list[str]:
    '''List the names of files and subdirectories directly inside a directory (non-recursive).'''
    return [p.name for p in _resolve(path).iterdir()]

if __name__ == "__main__":
    mcp.run(transport='stdio')
