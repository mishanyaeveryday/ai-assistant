# Configuration of API keys and paths
from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv('GROQ_API_KEY')

GROQ_MODEL = "llama-3.3-70b-versatile"

GENAI_API_KEY = os.getenv('GENAI_API_KEY')

GENAI_MODEL = "gemini-2.5-flash"

TOOLS_REQUIRING_APPROVAL: frozenset[str] = frozenset({"terminal_command"})

DOCKER_CONTAINER = os.getenv("DOCKER_CONTAINER")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY is not set in environment variables!")
