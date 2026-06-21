"""Embedded terminal: a PTY (persistent tmux) bridged to a WebSocket.

Gives a real root shell on the box inside the Agent Builder. Token-gated by the
cockpit and reached over the same Tailscale Funnel as the canvas. Full powers:
run git, the factory, `claude`, `docker exec` into Hubert, anything.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import termios

SHELL_CWD = "/root/.hermes/workspace/adk"


async def pty_bridge(websocket, cwd: str = SHELL_CWD) -> None:
    await websocket.accept()
    pid, fd = pty.fork()
    if pid == 0:  # child -> become the shell
        os.environ["TERM"] = "xterm-256color"
        try:
            os.chdir(cwd)
        except OSError:
            pass
        os.execvp("tmux", ["tmux", "new", "-A", "-s", "ops"])
        os._exit(1)

    loop = asyncio.get_event_loop()

    def _on_master():
        try:
            data = os.read(fd, 65536)
        except OSError:
            data = b""
        if data:
            loop.create_task(websocket.send_bytes(data))
        else:
            loop.remove_reader(fd)

    loop.add_reader(fd, _on_master)
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text")
            data = msg.get("bytes")
            if text:
                if text[0] == "\x00":  # resize control: \x00cols,rows
                    try:
                        cols, rows = (int(x) for x in text[1:].split(","))
                        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                    except (ValueError, OSError):
                        pass
                else:
                    os.write(fd, text.encode())
            elif data is not None:
                os.write(fd, data)
    except Exception:
        pass
    finally:
        try:
            loop.remove_reader(fd)
        except (ValueError, OSError):
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
