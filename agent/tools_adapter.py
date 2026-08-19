from collections.abc import Awaitable, Callable

from google.genai import types

from agent.tools_policy import ToolsApprovalPolicy

ApproveToolFn = Callable[[str, dict], Awaitable[bool]]


class ToolsAdapter:
    def __init__(
        self,
        mcp_client,
        tools_approval_policy: ToolsApprovalPolicy,
        approve_tool: ApproveToolFn | None = None,
    ):
        self.mcp_client = mcp_client
        self.tools_approval_policy = tools_approval_policy
        self.approve_tool = approve_tool

    def mcp_tools_to_gemini_declarations(self, mcp_tools):
        declaration = []
        for tool in mcp_tools:
            print(f'Tool name: {tool.name}, description: {tool.description}')
            d = types.FunctionDeclaration(
                name=tool.name, description=tool.description, parameters=tool.inputSchema)
            declaration.append(d)
        return types.Tool(function_declarations=declaration)

    async def call_and_format(self, name: str, args: dict):
        if self.tools_approval_policy.requires_approval(name):
            if self.approve_tool is None:
                return self._denial_part(
                    name, "Approval is required but no approve handler was configured."
                )
            allowed = await self.approve_tool(name, args or {})
            if not allowed:
                return self._denial_part(name, "User denied execution.")
        result = await self.mcp_client.call_tool(name, args or {})
        return types.Part.from_function_response(name=name, response={"result": result})

    @staticmethod
    def _denial_part(name: str, message: str):
        return types.Part.from_function_response(
            name=name,
            response={"ok": False, "error": message},
        )
