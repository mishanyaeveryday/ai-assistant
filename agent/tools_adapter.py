from google.genai import types


class ToolsAdapter:
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client

    def mcp_tools_to_gemini_declarations(self, mcp_tools):
        declaration = []
        for tool in mcp_tools:
            print(f'Tool name: {tool.name}, description: {tool.description}')
            d = types.FunctionDeclaration(
                name=tool.name, description=tool.description, parameters=tool.inputSchema)
            declaration.append(d)
        return types.Tool(function_declarations=declaration)

    async def call_and_format(self, name, args):
        result = await self.mcp_client.call_tool(name, args)

        return types.Part.from_function_response(
            name=name,
            response={'result': result}
        )
