from typing import Annotated
import asyncio
import platform
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("terminal-command")


@mcp.tool()
async def terminal_command(command: Annotated[str, "The command to execute in the terminal"]):
    f'''
    Use this tool to execute a terminal command.
    The command should be a valid terminal command for {platform.system()}, {platform.machine()}.
    '''
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
