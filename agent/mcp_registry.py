"""Ties the catalogue in the database to the running connections.

The model is offered the tools of every enabled connection, taken from the
cache, whether or not anything is running. When it calls one, the owning
server is looked up by tool name and started if needed - the model never
chooses a server, and never learns that servers have a running state.
"""
from agent.mcp_client import ConnectionSpec
from core.services import uses_openrouter


class MCPRegistry:
    def __init__(self, mcp_server_service, mcp_client, user_id: str | None = None,
                 model_settings=None):
        self._service = mcp_server_service
        self._client = mcp_client
        self.user_id = user_id
        self._owners: dict = {}
        # Gives the servers that call OpenRouter the user's key; without it
        # they read .env.
        self._model_settings = model_settings

    def set_user(self, user_id: str | None):
        """A new login must not inherit the previous user's servers."""
        self.user_id = user_id
        self._owners = {}

    async def set_workspace(self, path: str | None):
        """The folder tool calls work in from now on - set by each task to
        the workspace of its chat."""
        await self._client.set_workspace(path)

    async def get_tools(self):
        """The tool specs to offer the model, refreshed from the cache."""
        if not self.user_id:
            return []
        specs, self._owners = self._service.get_tool_catalogue(self.user_id)
        return specs

    def owner_of(self, tool_name: str):
        return self._owners.get(tool_name)

    def is_builtin_tool(self, tool_name: str) -> bool:
        """Tools from a server the user added are not covered by the built-in
        approval list, so callers need to be able to tell them apart."""
        owner = self._owners.get(tool_name)
        return bool(owner and owner.is_builtin)

    def is_auto_approved(self, tool_name: str) -> bool:
        """Whether the user lets this tool run without asking. Read from the
        database on each call rather than from the catalogue taken when the
        task started, so a change in settings counts straight away. Keyed on
        the server that owns the tool: one re-using another's tool name does
        not inherit its permission."""
        owner = self._owners.get(tool_name)
        if owner is None:
            return False
        server = self._service.get_server(owner.id)
        return server is not None and server.allows_without_asking(tool_name)

    async def stop_server(self, server_id: str) -> bool:
        """Shuts down a server that was switched off or removed in settings.
        Left running, it would keep serving calls - and a running connection
        is reused as-is, so it would never pick up a changed config."""
        return await self._client.disconnect(server_id)

    async def stop_openrouter_servers(self, user_id: str):
        """Shuts down this user's servers that call OpenRouter, after their
        key changed: they were started with the old one, and the next call
        starts them again with the new."""
        for server in self._service.get_user_servers(user_id):
            if uses_openrouter(server):
                await self._client.disconnect(server.id)

    def _openrouter_env(self, user_id: str) -> dict:
        api_key = self._model_settings.get_api_key(user_id)
        return {"OPENROUTER_API_KEY": api_key} if api_key else {}

    def _spec_for(self, server) -> ConnectionSpec:
        # Secrets are decrypted here and go straight into the spec that starts
        # the process. They are never written back to the row, and never put on
        # the MCPServer object callers can read field by field.
        env, _ = self._service.resolve_secrets(server.user_id, server.env)
        headers, _ = self._service.resolve_secrets(server.user_id, server.headers)
        if self._model_settings is not None and uses_openrouter(server):
            # Only to these: a server running shell commands would hand the
            # key to every command the model runs.
            env = {**(env or {}), **self._openrouter_env(server.user_id)}
        return ConnectionSpec(
            id=server.id,
            name=server.name,
            transport=server.transport,
            command=server.command,
            args=server.args,
            env=env,
            headers=headers,
            url=server.url,
        )

    async def call_tool(self, tool_name: str, arguments: dict):
        owner = self._owners.get(tool_name)
        if owner is None:
            # The catalogue may not have been built yet on this instance.
            await self.get_tools()
            owner = self._owners.get(tool_name)
        if owner is None:
            raise ValueError(
                f"No enabled MCP server provides a tool named '{tool_name}'")

        return await self._client.call_tool(
            self._spec_for(owner), tool_name, arguments or {})