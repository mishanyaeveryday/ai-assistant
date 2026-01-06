import asyncio
from typing import Optional
from contextlib import AsyncExitStack
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import sniffio
from langchain_google_genai import ChatGoogleGenerativeAI
from config.settings import GROQ_API_KEY, GROQ_MODEL, GENAI_API_KEY, GENAI_MODEL
from dotenv import load_dotenv
import os
import sys


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.llm = ChatGoogleGenerativeAI(
            model=GENAI_MODEL,
            google_api_key=GENAI_API_KEY
        )

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

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:",
              [tool.name for tool in tools])

    async def get_tools(self):
        if not self.session:
            return []
        response = await self.session.list_tools()
        return response.tools
