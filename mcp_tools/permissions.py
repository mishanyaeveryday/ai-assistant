"""Whether macOS lets the assistant see the screen and send input.

Both are granted to the app the assistant was started from - Terminal,
iTerm, Visual Studio Code - not to Python. Without them nothing fails:
clicks and key presses are silently dropped, and screenshots show only the
wallpaper and the assistant's own window. So the tools check first and say
what is missing instead of reporting a click that never happened.
"""
import ctypes
import platform
from functools import cache

IS_MAC = platform.system() == "Darwin"


@cache
def _function(framework: str, name: str):
    library = ctypes.cdll.LoadLibrary(
        f"/System/Library/Frameworks/{framework}.framework/{framework}")
    function = getattr(library, name)
    function.restype = ctypes.c_bool
    return function


def _allowed(framework: str, name: str) -> bool:
    # Only reads the setting: neither call shows the system's permission
    # dialog. Anything unexpected counts as allowed, so a check that cannot
    # run never blocks a tool that would have worked.
    try:
        return _function(framework, name)()
    except (OSError, AttributeError):
        return True


def missing_input_access() -> str | None:
    """Why clicks and key presses would be dropped, or None if they will go
    through."""
    if not IS_MAC or _allowed("ApplicationServices", "AXIsProcessTrusted"):
        return None
    return ("macOS has not given the assistant Accessibility access, so clicks and key presses "
            "would be silently dropped. Tell the user to turn it on in System Settings > Privacy & "
            "Security > Accessibility for the app they started the assistant from (Terminal, "
            "Visual Studio Code, ...), then restart the assistant.")


def missing_screen_access() -> str | None:
    """Why a screenshot would show only the wallpaper, or None if it will show
    the screen."""
    if not IS_MAC or _allowed("CoreGraphics", "CGPreflightScreenCaptureAccess"):
        return None
    return ("macOS has not given the assistant Screen Recording access, so a screenshot would show "
            "only the wallpaper and the assistant's own window. Tell the user to turn it on in "
            "System Settings > Privacy & Security > Screen Recording for the app they started the "
            "assistant from (Terminal, Visual Studio Code, ...), then restart the assistant.")
