from typing import Annotated
import asyncio
import platform
import pyautogui
import pyperclip

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("input-control")

pyautogui.FAILSAFE = True

PASTE_HOTKEY = ("command", "v") if platform.system() == "Darwin" else ("ctrl", "v")


@mcp.tool()
async def click(
    x: Annotated[int, "X pixel coordinate on screen to click, e.g. as found via read_image"],
    y: Annotated[int, "Y pixel coordinate on screen to click, e.g. as found via read_image"],
    button: Annotated[str, "Mouse button to use: 'left', 'right', or 'middle'"] = "left",
    clicks: Annotated[int, "Number of clicks, e.g. 2 for a double-click"] = 1,
) -> str:
    '''Move the mouse cursor to the given screen coordinates and click. Use read_image first to
    find where on the screen something is (it can report pixel coordinates), then click it here.'''
    try:
        await asyncio.to_thread(pyautogui.click, x=x, y=y, clicks=clicks, button=button)
    except Exception as e:
        return f"Failed to click at ({x}, {y}): {e}"
    return f"Clicked at ({x}, {y}) with {button} button x{clicks}"


@mcp.tool()
async def type_text(
    text: Annotated[str, "The text to type at the current keyboard focus (any language/Unicode)"],
) -> str:
    '''Type text wherever the keyboard focus currently is (e.g. after clicking into a text field).
    Types via the clipboard so any language/Unicode text works reliably, not just US-layout ASCII.
    Note: this overwrites the current clipboard contents.'''
    try:
        await asyncio.to_thread(pyperclip.copy, text)
        await asyncio.to_thread(pyautogui.hotkey, *PASTE_HOTKEY)
    except Exception as e:
        return f"Failed to type text: {e}"
    return f"Typed: {text}"


if __name__ == "__main__":
    mcp.run(transport='stdio')
