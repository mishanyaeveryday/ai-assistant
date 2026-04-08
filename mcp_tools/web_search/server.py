import os
import sys
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient

try:
    from config.settings import TAVILY_API_KEY
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from config.settings import TAVILY_API_KEY

mcp = FastMCP("web-search")
tavily = TavilyClient(api_key=TAVILY_API_KEY)


@mcp.tool()
async def web_search(query: Annotated[str, "The search query to look up on the internet"]):
    '''
    Use this tool to search the internet for recent or
    factual information when user asks about current events or
    general knowledge.
    '''
    try:
        # Tavily search
        response = tavily.search(
            query=query, search_depth="basic", max_results=5)

        results = []
        for result in response['results']:
            results.append(
                f"Source: {result['url']}\nContent: {result['content']}\n")

        return "\n---\n".join(results)
    except Exception as e:
        return f"Search error: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
