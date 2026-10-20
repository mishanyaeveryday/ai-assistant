# Configuration of API keys and paths
from dotenv import load_dotenv
from pathlib import Path
import os

# The .env next to main.py, wherever the app or an MCP server is started
# from. A bare load_dotenv() searches upward from this file and would stop at
# an old config/.env first.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", str(
    Path.home() / "ai-assistant-workspace"))

SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", str(
    Path.home() / "ai-assistant-screenshots"))

GROQ_API_KEY = os.getenv('GROQ_API_KEY')

GROQ_MODEL = "llama-3.3-70b-versatile"

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Any model id from https://openrouter.ai/models that supports tools.
LLM_MODEL = os.getenv('LLM_MODEL', "google/gemini-3.8-flash")

# Models OpenRouter switches to, in order, when LLM_MODEL fails - e.g.
# LLM_FALLBACK_MODELS=google/gemini-3.7-flash,openai/gpt-5-mini. Off by
# default: a fallback that answers mid-task is sent the first model's
# reasoning, which some models reject. A 503 from one provider is already
# retried by OpenRouter on another provider of the same model.
LLM_FALLBACK_MODELS = [m.strip() for m in os.getenv('LLM_FALLBACK_MODELS', '').split(',')
                       if m.strip()]

# Looks at images and screenshots for read_image; it must accept image input.
VISION_MODEL = os.getenv('VISION_MODEL', "google/gemini-3.8-flash")

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

# How many rounds of tool calls one prompt may take before the model has to
# answer with what it has. Searching and saving a summary alone takes several.
MAX_TOOL_ROUNDS = 25

DOCKER_CONTAINER = os.getenv("DOCKER_CONTAINER")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY is not set in environment variables!")
