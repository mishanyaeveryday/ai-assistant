"""Lazy runtime for MCP server connections.

Nothing is started up front. A tool call arrives, the owning connection is
brought up if it is not already running, and the call goes through. The model
is never aware that servers can be up or down - which connection owns a tool
is decided here, from the tool's name.

Connections that have not been used for a while are shut down again.
"""
import asyncio
import time
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from agent.mcp_probe import resolve_stdio_command

# How long a connection may sit unused before it is closed. Counted from the
# last call that went through it, not from when it started: a session ending
# is not something we get told about reliably.
IDLE_TIMEOUT_SECONDS = 10 * 60
IDLE_SWEEP_SECONDS = 60


@dataclass
class ConnectionSpec:
    """Everything needed to start one server. Built from a database row with
    its secrets already resolved, so this never holds a reference."""
    id: str
    name: str
    transport: str
    command: str | None = None
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    url: str | None = None
    headers: dict = field(default_factory=dict)


class _Connection:
    """One running server.

    It lives inside its own task on purpose: the underlying anyio context
    managers must be entered and exited by the same task, so closing a single
    connection from elsewhere (the idle sweep) would otherwise blow up with a
    cancel-scope error.
    """

    def __init__(self, spec: ConnectionSpec):
        self.spec = spec
        self.session: ClientSession | None = None
        self.last_used = time.monotonic()
        self.error: BaseException | None = None
        self._ready = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self.session is not None

    def _open(self):
        if self.spec.transport == "stdio":
            params = StdioServerParameters(
                command=resolve_stdio_command(self.spec.command, self.spec.args),
                args=list(self.spec.args or []),
                env=dict(self.spec.env) if self.spec.env else None,
            )
            return stdio_client(params)
        if self.spec.transport == "http":
            return streamable_http_client(
                url=self.spec.url,
                headers=dict(self.spec.headers) if self.spec.headers else None,
            )
        raise ValueError(f"Unknown transport {self.spec.transport!r}")

    async def _run(self):
        try:
            async with self._open() as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.session = session
                    self._ready.set()
                    await self._shutdown.wait()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:        # noqa: BLE001 - surfaced by start()
            self.error = exc
        finally:
            self.session = None
            self._ready.set()               # unblock a start() waiting on us

    async def start(self):
        self._task = asyncio.create_task(
            self._run(), name=f"mcp-connection-{self.spec.name}")
        await self._ready.wait()
        if self.error is not None:
            raise self.error
        if self.session is None:
            raise RuntimeError(f"Server {self.spec.name!r} closed during startup")

    async def stop(self):
        self._shutdown.set()
        if self._task is not None:
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def list_tools(self):
        response = await self.session.list_tools()
        return response.tools

    async def call_tool(self, tool_name: str, arguments: dict):
        self.last_used = time.monotonic()
        return await self.session.call_tool(name=tool_name, arguments=arguments)


class MCPClient:
    def __init__(self, idle_timeout: float = IDLE_TIMEOUT_SECONDS):
        self.idle_timeout = idle_timeout
        self._connections: dict[str, _Connection] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, server_id: str) -> asyncio.Lock:
        # Two calls landing on the same cold server must not start it twice.
        if server_id not in self._locks:
            self._locks[server_id] = asyncio.Lock()
        return self._locks[server_id]

    @property
    def active_ids(self) -> set[str]:
        return {sid for sid, c in self._connections.items() if c.is_running}

    async def ensure_connected(self, spec: ConnectionSpec) -> _Connection:
        async with self._lock_for(spec.id):
            connection = self._connections.get(spec.id)
            if connection is not None and connection.is_running:
                return connection

            connection = _Connection(spec)
            try:
                await connection.start()
            except BaseException:
                self._connections.pop(spec.id, None)
                raise
            self._connections[spec.id] = connection
            print(f"[MCP] Started {spec.name}")
            return connection

    async def call_tool(self, spec: ConnectionSpec, tool_name: str, arguments: dict):
        connection = await self.ensure_connected(spec)
        return await connection.call_tool(tool_name, arguments or {})

    async def list_tools(self, spec: ConnectionSpec):
        connection = await self.ensure_connected(spec)
        return await connection.list_tools()

    async def disconnect(self, server_id: str) -> bool:
        connection = self._connections.pop(server_id, None)
        if connection is None:
            return False
        await connection.stop()
        return True

    async def close_idle(self) -> list[str]:
        """Shuts down connections nothing has used recently. Returns the names
        that were closed."""
        now = time.monotonic()
        stale = [sid for sid, c in self._connections.items()
                 if now - c.last_used >= self.idle_timeout]
        closed = []
        for server_id in stale:
            name = self._connections[server_id].spec.name
            if await self.disconnect(server_id):
                closed.append(name)
                print(f"[MCP] Stopped {name} after "
                      f"{self.idle_timeout / 60:.0f} min idle")
        return closed

    async def close_all(self):
        for server_id in list(self._connections):
            await self.disconnect(server_id)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("\n[MCP] Cleaning up resources and closing servers...")
        await self.close_all()