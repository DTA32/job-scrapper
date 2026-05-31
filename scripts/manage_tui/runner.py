"""Async, gated subprocess sequence runner.

Runs a list[Command] in order, stopping on the first non-zero exit. Output is
streamed line-by-line to a callback. One sequence runs at a time. Cancellation
terminates the live child and always awaits it so no zombie is left behind.

Child env forces BUILDKIT_PROGRESS=plain; together with the lack of a TTY under
create_subprocess_exec, BuildKit emits plain lines instead of ANSI progress
bars that would corrupt the log widget.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

from .commands import Command
from .model import REPO_ROOT

LineCallback = Callable[[str], None]

_CANCELLED_RC = 130
_BINARY_MISSING_RC = 127

# asyncio's StreamReader caps a single line at 64 KiB by default. Docker's
# layer-pull progress overwrites one line with carriage returns and no newline,
# so a "line" can blow past that and raise LimitOverrunError, killing the run.
# Raise the ceiling well past any realistic plain-progress / log line.
_STREAM_LIMIT = 8 * 1024 * 1024  # 8 MiB


class SequenceRunner:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._cancelled = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None

    async def run(self, sequence: list[Command], on_line: LineCallback) -> int:
        self._cancelled = False
        child_env = {**os.environ, "BUILDKIT_PROGRESS": "plain"}
        for index, command in enumerate(sequence, start=1):
            if self._cancelled:
                on_line("^ cancelled before next step")
                return _CANCELLED_RC
            on_line(f"$ {command.preview()}")
            returncode = await self._run_one(command, child_env, on_line)
            if returncode != 0:
                verb = "cancelled" if self._cancelled else f"exited {returncode}"
                on_line(f"x step {index} {verb}; stopping")
                return returncode
        on_line("done.")
        return 0

    async def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        await proc.wait()

    async def _run_one(
        self, command: Command, child_env: dict[str, str], on_line: LineCallback
    ) -> int:
        stdout_file = None
        try:
            if command.stdout_path is not None:
                # held open across the await; closed in the finally below
                stdout_file = open(command.stdout_path, "wb")  # noqa: SIM115
                proc = await asyncio.create_subprocess_exec(
                    *command.argv,
                    cwd=REPO_ROOT,
                    stdout=stdout_file,
                    stderr=asyncio.subprocess.PIPE,
                    env=child_env,
                    limit=_STREAM_LIMIT,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *command.argv,
                    cwd=REPO_ROOT,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=child_env,
                    limit=_STREAM_LIMIT,
                )
        except FileNotFoundError as exc:
            on_line(f"x command not found: {command.argv[0]} ({exc.strerror})")
            return _BINARY_MISSING_RC

        self._proc = proc
        try:
            stream = proc.stderr if command.stdout_path is not None else proc.stdout
            assert stream is not None
            async for raw in stream:
                on_line(raw.decode(errors="replace").rstrip("\r\n"))
            await proc.wait()
            return proc.returncode if proc.returncode is not None else 0
        finally:
            if stdout_file is not None:
                stdout_file.close()
            self._proc = None
