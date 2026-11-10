from typing import Annotated
import asyncio
import os
import platform
import sys
import pyautogui
import pyperclip

from mcp.server.fastmcp import FastMCP

try:
    from mcp_tools.permissions import missing_input_access
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sys.path.insert(0, project_root)
    from mcp_tools.permissions import missing_input_access

mcp = FastMCP("input-control")

# Moving the mouse into a corner of the screen makes the next action raise
# FailSafeException: it is how the user stops screen control, since the steps
# don't ask first.
pyautogui.FAILSAFE = True
_STOPPED = ("Stopped: the user moved the mouse into a corner of the screen to stop screen control. "
            "No mouse or keyboard action will run until they turn screen control off and on again "
            "in Settings. Tell the user and wait for them.")
# Set by the first failsafe and kept until this server process restarts -
# which turning screen control off and on again does. Otherwise the user
# would have to hold the mouse in the corner: the next step would go through
# as soon as it left.
_stopped_by_user = False

IS_MAC = platform.system() == "Darwin"
PASTE_HOTKEY = ("command", "v") if IS_MAC else ("ctrl", "v")

# Key names models reach for that pyautogui spells differently.
_KEY_ALIASES = {
    "cmd": "command",
    "control": "ctrl",
    "opt": "option",
    "super": "command" if IS_MAC else "win",
    "meta": "command" if IS_MAC else "win",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "spacebar": "space",
}


def _refusal() -> str | None:
    """Why no input may be sent right now, or None."""
    if _stopped_by_user:
        return _STOPPED
    return missing_input_access()


def _stop() -> str:
    global _stopped_by_user
    _stopped_by_user = True
    return _STOPPED


def _off_screen(x: int, y: int) -> str | None:
    """Why a point can't be used, or None. pyautogui would quietly move it to
    the screen's edge instead - which hides a point taken off an image bigger
    than the screen, such as a Retina screenshot."""
    width, height = pyautogui.size()
    if 0 <= x < width and 0 <= y < height:
        return None
    return (f"({x}, {y}) is outside the screen, which is {width}x{height}. "
            "Get the point from find_on_screen.")


async def _focus(x: int | None, y: int | None) -> str | None:
    """Clicks the point first, if one is given, to put the keyboard focus back
    on the target - approving a call in the assistant's window takes it away.
    Returns why it could not, or None."""
    if x is None and y is None:
        return None
    if x is None or y is None:
        return "Give both x and y, or neither."
    problem = _off_screen(x, y)
    if problem:
        return problem
    await asyncio.to_thread(pyautogui.click, x=x, y=y)
    return None


@mcp.tool()
async def click(
    x: Annotated[int, "X coordinate on screen, from find_on_screen"],
    y: Annotated[int, "Y coordinate on screen, from find_on_screen"],
    button: Annotated[str, "Mouse button to use: 'left', 'right', or 'middle'"] = "left",
    clicks: Annotated[int, "Number of clicks, e.g. 2 for a double-click"] = 1,
) -> str:
    '''Move the mouse cursor to a point on the screen and click. Get the point from
    find_on_screen - its coordinates are the ones this takes; never estimate them.'''
    problem = _refusal() or _off_screen(x, y)
    if problem:
        return problem
    try:
        await asyncio.to_thread(pyautogui.click, x=x, y=y, clicks=clicks, button=button)
    except pyautogui.FailSafeException:
        return _stop()
    except Exception as e:
        return f"Failed to click at ({x}, {y}): {e}"
    return f"Clicked at ({x}, {y}) with {button} button x{clicks}"


@mcp.tool()
async def type_text(
    text: Annotated[str, "The text to type at the current keyboard focus (any language/Unicode)"],
    x: Annotated[int | None, "Optional: click this point first to focus the field (from find_on_screen)"] = None,
    y: Annotated[int | None, "Optional: click this point first to focus the field (from find_on_screen)"] = None,
) -> str:
    '''Type text wherever the keyboard focus is - pass the field's x and y to click into it first,
    since the focus may have moved to another window. Types via the clipboard so any
    language/Unicode text works reliably, not just US-layout ASCII. Note: this overwrites the
    current clipboard contents. Use press_keys('enter') afterwards to submit.'''
    problem = _refusal()
    if problem:
        return problem
    try:
        problem = await _focus(x, y)
        if problem:
            return problem
        await asyncio.to_thread(pyperclip.copy, text)
        await asyncio.to_thread(pyautogui.hotkey, *PASTE_HOTKEY)
    except pyautogui.FailSafeException:
        return _stop()
    except Exception as e:
        return f"Failed to type text: {e}"
    return f"Typed: {text}"


@mcp.tool()
async def press_keys(
    keys: Annotated[str, "One key, or a shortcut with its keys joined by '+': 'enter', 'escape', "
                         "'tab', 'down', 'command+c', 'command+shift+t'"],
    times: Annotated[int, "How many times to press it, e.g. 3 to move down three items"] = 1,
    x: Annotated[int | None, "Optional: click this point first to focus the right window or field "
                             "(from find_on_screen)"] = None,
    y: Annotated[int | None, "Optional: click this point first to focus the right window or field "
                             "(from find_on_screen)"] = None,
) -> str:
    '''Press a key or a keyboard shortcut at the keyboard focus - e.g. 'enter' to submit what
    type_text typed, 'escape' to close a dialog, 'command+tab' to switch apps.'''
    names = [_KEY_ALIASES.get(part, part) for part in
             (part.strip().lower() for part in keys.split("+"))]
    unknown = [name for name in names if name not in pyautogui.KEYBOARD_KEYS]
    if unknown:
        return (f"Unknown key(s): {', '.join(repr(name) for name in unknown)}. Use names like "
                "enter, escape, tab, space, backspace, up, down, command, ctrl, option, shift, f5.")
    if not 1 <= times <= 50:
        return "times must be between 1 and 50."
    problem = _refusal()
    if problem:
        return problem
    try:
        problem = await _focus(x, y)
        if problem:
            return problem
        for _ in range(times):
            # Pressed a little apart: macOS can miss a modifier sent together
            # with its key.
            await asyncio.to_thread(pyautogui.hotkey, *names, interval=0.05)
    except pyautogui.FailSafeException:
        return _stop()
    except Exception as e:
        return f"Failed to press {keys}: {e}"
    return f"Pressed {'+'.join(names)}" + (f" x{times}" if times > 1 else "")


@mcp.tool()
async def scroll(
    direction: Annotated[str, "'up' or 'down'"],
    amount: Annotated[int, "How far, in scroll-wheel steps; use more if the content barely moved"] = 5,
    x: Annotated[int | None, "Optional: scroll at this point - over the page or list to scroll "
                             "(from find_on_screen)"] = None,
    y: Annotated[int | None, "Optional: scroll at this point - over the page or list to scroll "
                             "(from find_on_screen)"] = None,
) -> str:
    '''Scroll the content under the mouse - or at x, y if given - up or down.'''
    if direction not in ("up", "down"):
        return "direction must be 'up' or 'down'."
    if not 1 <= amount <= 100:
        return "amount must be between 1 and 100."
    if (x is None) != (y is None):
        return "Give both x and y, or neither."
    problem = _refusal()
    if problem:
        return problem
    if x is not None:
        problem = _off_screen(x, y)
        if problem:
            return problem
    try:
        await asyncio.to_thread(pyautogui.scroll, amount if direction == "up" else -amount, x=x, y=y)
    except pyautogui.FailSafeException:
        return _stop()
    except Exception as e:
        return f"Failed to scroll: {e}"
    return f"Scrolled {direction} by {amount}" + (f" at ({x}, {y})" if x is not None else "")


if __name__ == "__main__":
    mcp.run(transport='stdio')