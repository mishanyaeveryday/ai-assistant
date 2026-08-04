from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self):
        # One session per connected server, plus a lookup from tool name to the session that owns it
        self.sessions: dict[str, ClientSession] = {}
        self.tool_to_session: dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))

        await session.initialize()
        self.sessions[server_script_path] = session

        # List available tools and remember which session owns each one
        response = await session.list_tools()
        for tool in response.tools:
            self.tool_to_session[tool.name] = session

        print("\nConnected to server with tools:",
              [tool.name for tool in response.tools])

    async def get_tools(self):
        all_tools = []
        for session in self.sessions.values():
            response = await session.list_tools()
            all_tools.extend(response.tools)
        return all_tools

    async def call_tool(self, tool_name, arguments):
        session = self.tool_to_session.get(tool_name)
        if session is None:
            raise ValueError(f"No connected MCP server exposes a tool named '{tool_name}'")
        result = await session.call_tool(name=tool_name, arguments=arguments)
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("\n[MCP] Cleaning up resources and closing servers...")
        await self.exit_stack.aclose()
