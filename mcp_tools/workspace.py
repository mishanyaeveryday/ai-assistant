"""Which folder a tool call works in.

The app sends the folder of the chat a task runs in as an MCP root, and the
servers ask for it on every call: a server outlives the chat that started it,
so the folder cannot be fixed when the process starts. A client that sends no
roots (the CLI, a connection check) gets WORKSPACE_DIR.
"""
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from mcp.server.fastmcp import Context
from mcp.types import ClientCapabilities, RootsCapability

from config.settings import WORKSPACE_DIR

DEFAULT_WORKSPACE = Path(WORKSPACE_DIR).expanduser().resolve()


def root_to_path(uri) -> Path:
    # A root is a file:// URI, with spaces and non-ASCII names percent-encoded,
    # so its path has to be decoded rather than read off as-is.
    return Path(url2pathname(urlparse(str(uri)).path))


async def resolve_workspace(ctx: Context | None) -> Path:
    roots = await _roots(ctx)
    if not roots:
        DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
        return DEFAULT_WORKSPACE

    workspace = root_to_path(roots[0].uri)
    # A folder the user picked is never recreated: had it been moved or
    # deleted, files written into a fresh empty one would just look lost.
    if not workspace.is_dir():
        raise FileNotFoundError(
            f"The workspace folder of this chat no longer exists: {workspace}. "
            "Ask the user to choose another one.")
    return workspace


async def _roots(ctx: Context | None) -> list:
    # No context when a tool function is called directly rather than over MCP.
    if ctx is None:
        return []
    session = ctx.session
    if not session.check_client_capability(ClientCapabilities(roots=RootsCapability())):
        return []
    return (await session.list_roots()).roots
