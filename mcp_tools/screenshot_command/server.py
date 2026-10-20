import base64
import io
import os
import sys
import mimetypes
from datetime import datetime
from functools import cache
from typing import Annotated
from PIL import ImageGrab
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import openai
from openai import AsyncOpenAI

try:
    from config.settings import (SCREENSHOT_DIR, WORKSPACE_DIR, OPENROUTER_API_KEY,
                                 OPENROUTER_BASE_URL, VISION_MODEL)
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from config.settings import (SCREENSHOT_DIR, WORKSPACE_DIR, OPENROUTER_API_KEY,
                                 OPENROUTER_BASE_URL, VISION_MODEL)

mcp = FastMCP("screenshot")


@cache
def _llm() -> AsyncOpenAI:
    # Built on first use: the SDK refuses to build a client without a key, and
    # the server must still start so the app can list its tools.
    if not OPENROUTER_API_KEY:
        raise openai.OpenAIError("OPENROUTER_API_KEY is not set in .env")
    # The SDK retries 429s and 5xx by itself, which covers a model that is
    # briefly overloaded.
    return AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL, max_retries=3)

WORKSPACE = Path(SCREENSHOT_DIR).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

FILES_WORKSPACE = Path(WORKSPACE_DIR).resolve()


def _resolve(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    return p


def _resolve_image(path: str) -> Path:
    """Resolve an image path: absolute paths are used as-is; relative
    ones are looked up in the screenshot dir first, then the workspace dir."""
    p = Path(path).expanduser()
    if p.is_absolute():
        return p.resolve()

    candidate = (WORKSPACE / p).resolve()
    if candidate.exists():
        return candidate

    return (FILES_WORKSPACE / p).resolve()


@mcp.tool()
async def make_screenshot(
    filename: Annotated[str,
                        "Name of the file to save the screenshot as, defaults to a timestamped name"] = ""
) -> str:
    '''Capture the current screen and save it as a PNG file.'''
    if not filename:
        filename = f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
    if not filename.lower().endswith(".png"):
        filename += ".png"

    p = _resolve(filename)
    img = ImageGrab.grab()
    img.save(p)
    return f"Screenshot saved to {p}"


@mcp.tool()
async def read_image(
    filename: Annotated[str,
                        "Name or path of the image to look at: a bare filename is looked up "
                        "in the screenshot dir then the workspace dir; an absolute path is used as-is. "
                        "Leave empty to capture and look at the current screen instead."] = "",
    question: Annotated[str,
                        "What to do with the image, e.g. 'extract the visible text', 'describe what's "
                        "shown', 'what error is displayed'. Defaults to a general description plus any text."] = ""
) -> str:
    '''Have the AI model look at an image directly (no OCR) and answer a question about it, or describe
    it and read out any visible text by default. Pass no filename to capture and look at the current
    screen; pass a filename (e.g. one made by make_screenshot) to look at that instead. Not just for
    text — use it to describe UI, diagrams, photos, whatever the user points to.'''
    if filename:
        p = _resolve_image(filename)
        if not p.exists():
            return f"File not found: {filename}"
        image_bytes = p.read_bytes()
        mime_type = mimetypes.guess_type(p.name)[0] or "image/png"
    else:
        buf = io.BytesIO()
        ImageGrab.grab().save(buf, format="PNG")
        image_bytes = buf.getvalue()
        mime_type = "image/png"

    prompt = question.strip() or (
        "Describe what is shown in this image, and separately list any text that is visible in it, "
        "exactly as it appears."
    )

    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"
    try:
        response = await _llm().chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ]}],
        )
    except openai.OpenAIError as e:
        message = str(e).lower()
        if isinstance(e, openai.APIStatusError) and any(
                kw in message for kw in ("image", "modalit", "mime", "unsupported")):
            return f"Model '{VISION_MODEL}' does not support reading images."
        return f"Failed to read image via the model: {e}"

    text = response.choices[0].message.content if response.choices else None
    return (text or "").strip() or "The model returned no output for this image."


if __name__ == "__main__":
    mcp.run(transport='stdio')
