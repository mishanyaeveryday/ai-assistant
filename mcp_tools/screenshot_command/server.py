import os
import sys
import cv2
import pytesseract
from datetime import datetime
from typing import Annotated
from PIL import ImageGrab
from pathlib import Path
from mcp.server.fastmcp import FastMCP

try:
    from config.settings import SCREENSHOT_DIR, WORKSPACE_DIR
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from config.settings import SCREENSHOT_DIR, WORKSPACE_DIR

mcp = FastMCP("screenshot")

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
async def read_screen_text() -> str:
    '''Capture the current screen and extract any visible text via OCR, without saving a screenshot file to disk.
    This only reads text on screen (labels, messages, code, etc.) — it cannot describe images, icons,
    colors, or layout.'''
    img = ImageGrab.grab().convert("L")
    text = pytesseract.image_to_string(img)
    return text.strip() or "No text detected on screen."


@mcp.tool()
async def read_image_text(
    filename: Annotated[str,
                        "Name or path of the image to read text from: a bare filename is looked up "
                        "in the screenshot dir then the workspace dir; an absolute path is used as-is"]
) -> str:
    '''Extract visible text from an image (e.g. a saved screenshot, or any other image file) using OCR.
    Use this after make_screenshot to find out what text is actually shown on screen, or on any
    other image the user points to.'''
    p = _resolve_image(filename)
    if not p.exists():
        return f"File not found: {filename}"

    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return f"Could not read image: {filename}"

    _, bw_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    text = pytesseract.image_to_string(bw_img)
    return text.strip() or "No text detected in the image."
