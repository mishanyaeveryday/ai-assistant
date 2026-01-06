from langchain.tools.tavily_search import TavilySearchResults
from config.settings import TAVILY_API_KEY
from langchain.tools import tool


search = TavilySearchResults(api_key=TAVILY_API_KEY)


@tool(
    description="Use this tool to search the internet for recent or factual information when user asks about current events or general knowledge."
)
def web_searching_tool(query: str) -> str:
    """
    Use this tool to search for current events or general knowledge online.
    """
    return search.run(query)
