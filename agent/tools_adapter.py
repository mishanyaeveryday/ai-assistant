import json
import re
from collections.abc import Awaitable, Callable

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

    def mcp_tools_to_openai_tools(self, mcp_tools) -> list[dict]:
        tools = []
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
            tools.append({"type": "function", "function": {
                "name": name, "description": description,
                # A tool without arguments still needs an object schema.
                "parameters": schema or {"type": "object", "properties": {}}}})
        return tools

    async def call_and_format(self, name: str, args: dict) -> str:
        """Runs the tool if allowed and returns what the model is shown."""
        is_builtin = self.mcp_registry.is_builtin_tool(name)
        if self.tools_approval_policy.requires_approval(name, is_builtin=is_builtin):
            if self.approve_tool is None:
                return error_result(
                    "Approval is required but no approve handler was configured.")
            allowed = await self.approve_tool(name, args or {})
            if not allowed:
                return error_result("User denied execution.")
        result = await self.mcp_registry.call_tool(name, args or {})
        self._collect_generated_images(result)
        return _result_text(result)

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


def error_result(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _result_text(result) -> str:
    """A tool result as text: the text blocks of an MCP result, one per line."""
    texts = []
    for content in getattr(result, "content", None) or []:
        text = getattr(content, "text", None)
        texts.append(text if text is not None
                     else f"[{getattr(content, 'type', 'unknown')} content]")
    text = "\n".join(texts)
    if not text and getattr(result, "structuredContent", None):
        text = json.dumps(result.structuredContent, ensure_ascii=False)
    if getattr(result, "isError", False):
        return error_result(text)
    return text or "(no output)"
