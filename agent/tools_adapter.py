import re
from collections.abc import Awaitable, Callable

from google.genai import types

from agent.tools_policy import ToolsApprovalPolicy

ApproveToolFn = Callable[[str, dict], Awaitable[bool]]

_IMAGE_MARKER_RE = re.compile(r"\[GENERATED_IMAGE:(.+?)\]")


class ToolsAdapter:
    def __init__(
        self,
        mcp_registry,
        tools_approval_policy: ToolsApprovalPolicy,
        approve_tool: ApproveToolFn | None = None,
    ):
        self.mcp_registry = mcp_registry
        self.tools_approval_policy = tools_approval_policy
        self.approve_tool = approve_tool
        self.generated_images: list[str] = []

    def mcp_tools_to_gemini_declarations(self, mcp_tools):
        declaration = []
        for tool in mcp_tools:
            # Cached catalogue entries are plain dicts; a caller passing live
            # MCP tool objects (selected_tool) still works.
            if isinstance(tool, dict):
                name = tool.get('name')
                description = tool.get('description') or ''
                schema = tool.get('inputSchema') or {}
            else:
                name, description, schema = (
                    tool.name, tool.description, tool.inputSchema)
            declaration.append(types.FunctionDeclaration(
                name=name, description=description, parameters=schema))
        return types.Tool(function_declarations=declaration)

    async def call_and_format(self, name: str, args: dict):
        is_builtin = self.mcp_registry.is_builtin_tool(name)
        if self.tools_approval_policy.requires_approval(name, is_builtin=is_builtin):
            if self.approve_tool is None:
                return self._denial_part(
                    name, "Approval is required but no approve handler was configured."
                )
            allowed = await self.approve_tool(name, args or {})
            if not allowed:
                return self._denial_part(name, "User denied execution.")
        result = await self.mcp_registry.call_tool(name, args or {})
        self._collect_generated_images(result)
        return types.Part.from_function_response(name=name, response={"result": result})

    def _collect_generated_images(self, result) -> None:
        """Pull out any [GENERATED_IMAGE:path] markers a tool left in its text
        output, remember the paths, and scrub the markers before the model
        sees them (it doesn't need the raw bracket syntax)."""
        for content in getattr(result, "content", None) or []:
            text = getattr(content, "text", None)
            if not text or "[GENERATED_IMAGE:" not in text:
                continue
            for match in _IMAGE_MARKER_RE.finditer(text):
                path = match.group(1).strip()
                if path:
                    self.generated_images.append(path)
            content.text = _IMAGE_MARKER_RE.sub("", text).strip()

    @staticmethod
    def _denial_part(name: str, message: str):
        return types.Part.from_function_response(
            name=name,
            response={"ok": False, "error": message},
        )
