from config.settings import TOOLS_REQUIRING_APPROVAL


class ToolsApprovalPolicy:
    def __init__(self, tool_names: frozenset[str] | None = None):
        self._tool_names = tool_names if tool_names is not None else TOOLS_REQUIRING_APPROVAL

    def requires_approval(self, tool_name: str) -> bool:
        return tool_name in self._tool_names
