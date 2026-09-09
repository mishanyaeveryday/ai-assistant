from config.settings import TOOLS_REQUIRING_APPROVAL


class ToolsApprovalPolicy:
    def __init__(self, tool_names: frozenset[str] | None = None):
        self._tool_names = tool_names if tool_names is not None else TOOLS_REQUIRING_APPROVAL

    def requires_approval(self, tool_name: str, is_builtin: bool = True) -> bool:
        """TOOLS_REQUIRING_APPROVAL only names the tools of the servers that
        ship with the app. A server the user added is arbitrary code, and its
        tools are absent from that list - so those ask by default rather than
        running unprompted."""
        if not is_builtin:
            return True
        return tool_name in self._tool_names
