from typing import Annotated
import asyncio
import platform
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("terminal-command")


@mcp.tool(description=(
    f"Execute a shell command on the user's machine ({platform.system()} {platform.machine()}). "
    "Use this for system-level actions that no other tool covers, e.g. opening applications, "
    "checking system info, or running scripts. Pass the full command exactly as it should be "
    "typed in a terminal on this OS. For reading, writing, appending, or deleting files, prefer "
    "the dedicated filesystem tools instead of shell commands."
))
async def terminal_command(command: Annotated[str, "The exact shell command to run, e.g. 'ls -la' or 'open -a Calculator'"]):
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout if proc.stdout else proc.stderr or ""
    except subprocess.CalledProcessError as e:
        out = getattr(e, "stderr", None) or getattr(e, "stdout", None) or str(e)
        return f"[exit {e.returncode}] {out}".strip()

if __name__ == "__main__":
    mcp.run(transport='stdio')
