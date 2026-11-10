import base64
import io
import json
import os
import re
import sys
import mimetypes
from datetime import datetime
from functools import cache
from typing import Annotated
from PIL import Image, ImageGrab
from pathlib import Path
from mcp.server.fastmcp import Context, FastMCP
import openai
import pyautogui
from openai import AsyncOpenAI

# The key is the user's from Settings > Model: the app starts this server with
# it in its environment, which wins over .env. The model is VISION_MODEL.
try:
    from config.settings import (SCREENSHOT_DIR, OPENROUTER_API_KEY,
                                 OPENROUTER_BASE_URL, VISION_MODEL)
    from core.openrouter import accepts_images, fetch_models
    from mcp_tools.permissions import missing_screen_access
    from mcp_tools.workspace import resolve_workspace
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from config.settings import (SCREENSHOT_DIR, OPENROUTER_API_KEY,
                                 OPENROUTER_BASE_URL, VISION_MODEL)
    from core.openrouter import accepts_images, fetch_models
    from mcp_tools.permissions import missing_screen_access
    from mcp_tools.workspace import resolve_workspace

mcp = FastMCP("screenshot")


@cache
def _llm() -> AsyncOpenAI:
    # Built on first use: the SDK refuses to build a client without a key, and
    # the server must still start so the app can list its tools.
    if not OPENROUTER_API_KEY:
        raise openai.OpenAIError(
            "There is no OpenRouter key - add one in Settings > Model, or "
            "OPENROUTER_API_KEY to .env")
    # The SDK retries 429s and 5xx by itself, which covers a model that is
    # briefly overloaded.
    return AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL, max_retries=3)


# Whether VISION_MODEL takes images, once OpenRouter has said so. The model is
# read from .env when the process starts and never changes after.
_sees_images_answer: bool | None = None


async def _sees_images() -> bool | None:
    """Whether the model can look at images, from OpenRouter's model list.
    None when that cannot be told - no connection, or a model it does not
    list - and the request is then simply tried."""
    global _sees_images_answer
    if _sees_images_answer is None:
        try:
            _sees_images_answer = accepts_images(await fetch_models(), VISION_MODEL)
        except Exception as e:
            print(f"Could not check whether {VISION_MODEL} takes images: {e}", file=sys.stderr)
    return _sees_images_answer


def _no_vision_message() -> str:
    # Meant for the calling model, which passes it on as a warning.
    return (f"The model '{VISION_MODEL}' cannot see images (it has no vision), so this tool "
            "cannot work with it. Warn the user about this and tell them to set VISION_MODEL "
            "in .env to a model that accepts images (google/gemini-3.8-flash by default). "
            "Do not retry, and do not guess what is on the screen or where.")

WORKSPACE = Path(SCREENSHOT_DIR).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _resolve(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    return p


async def _resolve_image(ctx: Context | None, path: str) -> Path:
    """Resolve an image path: absolute paths are used as-is; relative
    ones are looked up in the screenshot dir first, then the chat's
    workspace folder."""
    p = Path(path).expanduser()
    if p.is_absolute():
        return p.resolve()

    candidate = (WORKSPACE / p).resolve()
    if candidate.exists():
        return candidate

    return (await resolve_workspace(ctx) / p).resolve()


@mcp.tool()
async def make_screenshot(
    filename: Annotated[str,
                        "Name of the file to save the screenshot as, defaults to a timestamped name"] = ""
) -> str:
    '''Capture the current screen and save it as a PNG file.'''
    problem = missing_screen_access()
    if problem:
        return problem
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
                        "shown', 'what error is displayed'. Defaults to a general description plus any text."] = "",
    ctx: Context = None,
) -> str:
    '''Have the AI model look at an image directly (no OCR) and answer a question about it, or describe
    it and read out any visible text by default. Pass no filename to capture and look at the current
    screen; pass a filename (e.g. one made by make_screenshot) to look at that instead. Not just for
    text — use it to describe UI, diagrams, photos, whatever the user points to. Do not use it to
    get a point to click: its answers are not in screen coordinates - use find_on_screen.'''
    if filename:
        p = await _resolve_image(ctx, filename)
        if not p.exists():
            return f"File not found: {filename}"
        image_bytes = p.read_bytes()
        mime_type = mimetypes.guess_type(p.name)[0] or "image/png"
    else:
        problem = missing_screen_access()
        if problem:
            return problem
        buf = io.BytesIO()
        ImageGrab.grab().save(buf, format="PNG")
        image_bytes = buf.getvalue()
        mime_type = "image/png"

    prompt = question.strip() or (
        "Describe what is shown in this image, and separately list any text that is visible in it, "
        "exactly as it appears."
    )

    try:
        text = await _ask_vision(image_bytes, mime_type, prompt)
    except RuntimeError as e:
        return str(e)
    return text or "The model returned no output for this image."


@mcp.tool()
async def find_on_screen(
    target: Annotated[str,
                      "What to find, described as it looks, e.g. 'the blue Send button' or "
                      "'the search field at the top of the Safari window'"],
) -> str:
    '''Find something on the current screen and return the point to click it, in exactly the
    coordinates click(), scroll() and the x/y of type_text() and press_keys() take. Use this every
    time you need a point - never estimate coordinates yourself or from read_image. Only the main
    screen is looked at.'''
    problem = missing_screen_access()
    if problem:
        return problem
    screen = tuple(pyautogui.size())
    try:
        image = ImageGrab.grab()
    except Exception as e:
        return f"Could not capture the screen: {e}"
    # A Retina screen is captured at twice the size click() works in. The
    # answer is a fraction of the screen either way, so the image only needs
    # to be big enough to see - and smaller is quicker to send.
    if image.size != screen:
        image = image.resize(screen, Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    try:
        answer = await _ask_vision(buf.getvalue(), "image/png", _LOCATE_PROMPT.format(target=target))
    except RuntimeError as e:
        return str(e)
    try:
        x, y = point_from_answer(answer, screen)
    except LookupError as e:
        return f"Not found on screen: {target}. {e}"
    except ValueError as e:
        return f"The model's answer could not be read as a position ({e}). Try describing the target differently."
    return f"Found {target!r} at x={x}, y={y}."


# Asks for a box normalised to 0-1000 - the format Gemini models are trained
# on - so the answer does not depend on the size of the image the model saw.
_LOCATE_PROMPT = """Find this on the screenshot: {target}

Answer with JSON only. If it is visible:
{{"box_2d": [ymin, xmin, ymax, xmax]}}
the box around it, every value from 0 to 1000: x from the left edge (0) to the right edge (1000), \
y from the top edge (0) to the bottom edge (1000).
If it is not visible:
{{"found": false, "reason": "<what the screen shows instead>"}}"""


def _json_in(answer: str):
    """The first JSON value in a model's answer - which may come inside a code
    fence, or with words around it."""
    text = (answer or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"no JSON in {answer!r}")
    value, _ = json.JSONDecoder().raw_decode(text[min(starts):])
    return value


def point_from_answer(answer: str, screen: tuple[int, int]) -> tuple[int, int]:
    """The centre of the box the vision model found, in screen points. Raises
    LookupError carrying the model's reason when it says the target is not
    there, and ValueError when the answer is not a usable box."""
    data = _json_in(answer)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        # Gemini tends to answer a list of detections; the first is its best.
        data = data[0]
    if isinstance(data, dict):
        if data.get("found") is False:
            raise LookupError(data.get("reason") or "The model did not see it.")
        box = data.get("box_2d")
    else:
        box = data
    if not (isinstance(box, list) and len(box) == 4
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box)):
        raise ValueError(f"not a box: {box!r}")
    ymin, xmin, ymax, xmax = box
    if not (0 <= ymin <= ymax <= 1000 and 0 <= xmin <= xmax <= 1000):
        raise ValueError(f"box out of range: {box!r}")
    width, height = screen
    return (round((xmin + xmax) / 2 / 1000 * width),
            round((ymin + ymax) / 2 / 1000 * height))


async def _ask_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    """One image and a question to VISION_MODEL; returns its answer. Raises
    RuntimeError with a message the calling model can act on."""
    # Checked before sending: a model without vision may not refuse the
    # image, but answer without having seen it.
    if await _sees_images() is False:
        raise RuntimeError(_no_vision_message())
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
            raise RuntimeError(_no_vision_message()) from None
        raise RuntimeError(f"Failed to read image via the model: {e}") from None

    text = response.choices[0].message.content if response.choices else None
    return (text or "").strip()


if __name__ == "__main__":
    mcp.run(transport='stdio')
