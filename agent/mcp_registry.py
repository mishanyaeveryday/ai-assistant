"""Ties the catalogue in the database to the running connections.

The model is offered the tools of every enabled connection, taken from the
cache, whether or not anything is running. When it calls one, the owning
server is looked up by tool name and started if needed - the model never
chooses a server, and never learns that servers have a running state.
"""
from agent.mcp_client import ConnectionSpec


class MCPRegistry:
    def __init__(self, mcp_server_service, mcp_client, user_id: str | None = None):
        self._service = mcp_server_service
        self._client = mcp_client
        self.user_id = user_id
        self._owners: dict = {}

    def set_user(self, user_id: str | None):
        """A new login must not inherit the previous user's servers."""
        self.user_id = user_id
        self._owners = {}

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

    async def stop_server(self, server_id: str) -> bool:
        """Shuts down a server that was switched off or removed in settings.
        Left running, it would keep serving calls - and a running connection
        is reused as-is, so it would never pick up a changed config."""
        return await self._client.disconnect(server_id)

    def _spec_for(self, server) -> ConnectionSpec:
        # Secrets are decrypted here and go straight into the spec that starts
        # the process. They are never written back to the row, and never put on
        # the MCPServer object callers can read field by field.
        env, _ = self._service.resolve_secrets(server.user_id, server.env)
        headers, _ = self._service.resolve_secrets(server.user_id, server.headers)
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