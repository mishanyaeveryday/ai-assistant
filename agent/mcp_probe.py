"""Connection checks for MCP servers.

A probe performs the same handshake the real client does - connect, initialize,
list tools - and reports back a short error code instead of raising, so a
broken server can be recorded and switched off rather than taking the app down.
"""
import asyncio
import sys
import tempfile
from dataclasses import dataclass, field

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

PROBE_TIMEOUT_SECONDS = 15.0
# How much of a crashed server's stderr to keep. The bottom of a traceback is
# the useful part, and this text is stored in the row and shown to the user.
STDERR_TAIL_LINES = 10

STATUS_OK = "ok"
STATUS_ERROR = "error"


@dataclass
class ProbeResult:
    ok: bool
    code: str
    message: str
    tools: tuple[str, ...] = field(default_factory=tuple)
    # Full definitions (name/description/inputSchema). Cached on the server row
    # so the model can be offered the tools without anything being running.
    tool_specs: tuple[dict, ...] = field(default_factory=tuple)


def resolve_stdio_command(command: str | None, args: list | None) -> str:
    """Built-in servers store no command on purpose - the interpreter is
    resolved at launch time so the rows survive a rebuilt virtualenv. This
    is derived from the script name, the same way the runtime does it."""
    if command:
        return command
    script = args[0] if args else ""
    return "node" if str(script).endswith(".js") else sys.executable


def _leaf_exceptions(exc: BaseException):
    """anyio task groups wrap failures in ExceptionGroups, so the cause has to
    be dug out before it can be classified."""
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            yield from _leaf_exceptions(sub)
    else:
        yield exc


def _is_being_cancelled(exc: BaseException) -> bool:
    """Cancelling a probe (logout, or a second login) tears the transport down
    mid-handshake, which surfaces as an ordinary transport error such as
    BrokenResourceError. Recording that would disable a perfectly good server,
    so cancellation has to be told apart from a real failure."""
    if any(isinstance(leaf, asyncio.CancelledError)
           for leaf in _leaf_exceptions(exc)):
        return True
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


def _classify(exc: BaseException) -> tuple[str, str]:
    for leaf in _leaf_exceptions(exc):
        if isinstance(leaf, httpx.HTTPStatusError):
            return f"http_{leaf.response.status_code}", str(leaf)
        if isinstance(leaf, httpx.ConnectTimeout):
            return "timeout", "Timed out connecting to the server."
        if isinstance(leaf, httpx.ConnectError):
            return "connect_failed", str(leaf)
        if isinstance(leaf, httpx.InvalidURL):
            return "invalid_url", str(leaf)
        if isinstance(leaf, FileNotFoundError):
            return "spawn_failed", f"Could not run the server: {leaf}"
        if isinstance(leaf, PermissionError):
            return "spawn_failed", f"Not allowed to run the server: {leaf}"
        if isinstance(leaf, (asyncio.TimeoutError, TimeoutError)):
            return "timeout", "The server did not respond in time."

    first = next(_leaf_exceptions(exc), exc)
    return "error", f"{type(first).__name__}: {first}"


def _tool_spec(tool) -> dict:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "inputSchema": tool.inputSchema or {},
    }


async def _handshake(read, write) -> ProbeResult:
    async with ClientSession(read, write) as session:
        await session.initialize()
        response = await session.list_tools()
        specs = tuple(_tool_spec(tool) for tool in response.tools)
    names = tuple(spec["name"] for spec in specs)
    return ProbeResult(True, STATUS_OK, f"{len(names)} tool(s) available",
                       names, specs)


def _tail(text: str, lines: int = STDERR_TAIL_LINES) -> str:
    kept = [line for line in text.strip().splitlines() if line.strip()][-lines:]
    return "\n".join(kept)


async def _probe_stdio(command, args, env) -> ProbeResult:
    if not args and not command:
        return ProbeResult(False, "invalid_config",
                           "This stdio server has no command or arguments to run.")

    params = StdioServerParameters(
        command=resolve_stdio_command(command, args),
        args=list(args or []),
        env=dict(env) if env else None,
    )

    # A server that dies on startup only says "Connection closed" through the
    # protocol; its traceback goes to stderr, which is the part worth showing.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errlog:
        try:
            async with stdio_client(params, errlog=errlog) as (read, write):
                return await _handshake(read, write)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:        # noqa: BLE001 - reported, not raised
            if _is_being_cancelled(exc):
                raise asyncio.CancelledError from exc
            code, message = _classify(exc)
            try:
                errlog.seek(0)
                stderr = _tail(errlog.read())
            except (OSError, ValueError):
                stderr = ""
            return ProbeResult(False, code,
                               f"{message}\n{stderr}" if stderr else message)


async def _probe_http(url, headers) -> ProbeResult:
    if not url:
        return ProbeResult(False, "invalid_config", "This http server has no URL.")

    async with streamable_http_client(
        url=url,
        headers=dict(headers) if headers else None,
        timeout=PROBE_TIMEOUT_SECONDS,
    ) as (read, write, _get_session_id):
        return await _handshake(read, write)


async def probe(transport: str, *, command=None, args=None, env=None,
                url=None, headers=None,
                timeout: float = PROBE_TIMEOUT_SECONDS) -> ProbeResult:
    """Runs the transport-appropriate check. Never raises: every failure comes
    back as a ProbeResult carrying an error code."""
    if transport == "stdio":
        coro = _probe_stdio(command, args, env)
    elif transport == "http":
        coro = _probe_http(url, headers)
    else:
        return ProbeResult(False, "unsupported_transport",
                           f"Unknown transport {transport!r}.")

    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        return ProbeResult(False, "timeout",
                           f"No response within {timeout:.0f}s.")
    except asyncio.CancelledError:
        raise
    except BaseException as exc:            # noqa: BLE001 - reported, not raised
        if _is_being_cancelled(exc):
            raise asyncio.CancelledError from exc
        code, message = _classify(exc)
        return ProbeResult(False, code, message)
