# Configuration of API keys and paths
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", str(
    Path.home() / "ai-assistant-workspace"))

SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", str(
    Path.home() / "ai-assistant-screenshots"))

GROQ_API_KEY = os.getenv('GROQ_API_KEY')

GROQ_MODEL = "llama-3.3-70b-versatile"

GENAI_API_KEY = os.getenv('GENAI_API_KEY')

GENAI_MODEL = "gemini-2.5-flash"

# The MCP servers that ship with the app. They are seeded into the
# mcp_servers table for every user and connected at startup, so this tuple is
# the single source for both. Paths are relative to the project root, which is
# where the app is expected to be launched from.
BUILTIN_MCP_SERVERS: tuple[dict, ...] = (
    {"name": "web_search",
     "script": "mcp_tools/web_search/server.py",
     "description": "Web search"},
    {"name": "terminal_command",
     "script": "mcp_tools/terminal_command/server.py",
     "description": "Runs terminal commands"},
    {"name": "filesystem_command",
     "script": "mcp_tools/filesystem_command/server.py",
     "description": "Reads and writes files"},
    {"name": "screenshot_command",
     "script": "mcp_tools/screenshot_command/server.py",
     "description": "Takes screenshots"},
    {"name": "input_control",
     "script": "mcp_tools/input_control/server.py",
     "description": "Controls the cursor and keyboard"},
    {"name": "code_interpreter",
     "script": "mcp_tools/code_interpreter/server.py",
     "description": "Runs Python code"},
)

TOOLS_REQUIRING_APPROVAL: frozenset[str] = frozenset(
    {"terminal_command", "write_file", "delete_file", "append_file", "delete_text", "make_screenshot",
     "click", "type_text", "run_python_code"})

DOCKER_CONTAINER = os.getenv("DOCKER_CONTAINER")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY is not set in environment variables!")
