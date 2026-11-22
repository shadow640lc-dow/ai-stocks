"""Process runner, background calls and the app-wide signal bus."""

from __future__ import annotations

import os
import re
import shutil
import signal
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, QTimer, Signal

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][A-Za-z0-9]")


def clean(text: str) -> str:
    """Strip terminal escape sequences from engine output."""
    return ANSI_RE.sub("", text).replace("\r", "")


def _descendant_pids(root: int) -> list[int]:
    """Read /proc once and return the process tree below ``root``."""
    children: dict[int, list[int]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        close = stat.rfind(")")
        if close < 0:
            continue
        fields = stat[close + 2 :].split()
        if len(fields) < 2:
            continue
        try:
            parent = int(fields[1])
        except ValueError:
            continue
        children.setdefault(parent, []).append(pid)

    out: list[int] = []
    stack = [root]
    while stack:
        parent = stack.pop()
        for child in children.get(parent, []):
            out.append(child)
            stack.append(child)
    return out


class Bus(QObject):
    """Tiny global event bus shared by the shell and the pages."""

    activity = Signal(str, str)      # engine, message
    switch_changed = Signal(bool)    # master kill switch


bus = Bus()


class ProcessRunner(QObject):
    """Runs one engine at a time and streams merged stdout/stderr."""

    output = Signal(str)
    exited = Signal(int)
    started = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._buffer = ""
        self._done = True

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self._group_started = False

    # -- state ---------------------------------------------------------

    def busy(self) -> bool:
        return self.proc.state() != QProcess.ProcessState.NotRunning

    # -- control -------------------------------------------------------

    def start(self, argv: list[str], cwd: Path | str | None = None) -> bool:
        if self.busy():
            return False

        env = QProcessEnvironment.systemEnvironment()
        parts = [p for p in env.value("PATH", "").split(":") if p]
        for extra in (str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin", "/bin"):
            if extra not in parts:
                parts.append(extra)
        env.insert("PATH", ":".join(parts))
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("COLUMNS", "120")
        env.insert("LINES", "40")
        env.insert("MEGATRON_GUI", "1")
        env.insert("MEGATRON_NONINTERACTIVE", "1")
        self.proc.setProcessEnvironment(env)

        if cwd:
            self.proc.setWorkingDirectory(str(cwd))

        self._buffer = ""
        self._done = False
        self._group_started = False
        command = list(argv)
        if os.name == "posix":
            # setsid gives the engine its own process group. Closing MEGATRON
            # then kills poetry *and* the Python engine, not just the wrapper.
            setsid = shutil.which("setsid")
            if setsid:
                command = [setsid, *command]
                self._group_started = True
        self.started.emit(" ".join(argv))
        self.proc.start(command[0], command[1:])
        return True

    def send(self, text: str) -> None:
        if self.busy():
            self.proc.write((text + "\n").encode("utf-8"))

    def stop(self) -> None:
        if not self.busy():
            return
        self._signal_group(signal.SIGTERM)
        QTimer.singleShot(2500, self._force_kill)

    def shutdown(self, wait_ms: int = 3500) -> None:
        """Terminate the engine and its whole process group before exit."""
        if not self.busy():
            return
        self._signal_group(signal.SIGTERM)
        if self.proc.waitForFinished(2000):
            return
        self._signal_group(signal.SIGKILL)
        self.proc.waitForFinished(max(250, wait_ms - 2000))

    def _signal_group(self, sig: int) -> None:
        pid = int(self.proc.processId() or 0)
        if os.name == "posix" and pid > 0:
            if self._group_started:
                try:
                    os.killpg(pid, sig)
                    self._wait_for_pid(pid)
                    return
                except (ProcessLookupError, PermissionError, OSError):
                    pass
            # Fallback for builds without setsid: deepest children first.
            for child in reversed(_descendant_pids(pid)):
                try:
                    os.kill(child, sig)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
        if sig == signal.SIGKILL:
            self.proc.kill()
        else:
            self.proc.terminate()

    @staticmethod
    def _wait_for_pid(pid: int) -> None:
        for _ in range(10):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            except OSError:
                return
            QThread.msleep(20)

    def _force_kill(self) -> None:
        if self.busy():
            self._signal_group(signal.SIGKILL)

    # -- internals -----------------------------------------------------

    def _read(self) -> None:
        chunk = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        if not chunk:
            return
        self._buffer += chunk
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = clean(line)
            if line.strip():
                self.output.emit(line)

    def _finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        if self._done:
            return
        self._done = True
        leftover = clean(self._buffer).strip()
        self._buffer = ""
        if leftover:
            self.output.emit(leftover)
        self.exited.emit(int(code))

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and not self._done:
            self._done = True
            self.output.emit(f"✖ Could not start: {self.proc.program()}")
            self.exited.emit(127)


class CallThread(QThread):
    """Run one blocking call (HTTP quote, balance lookup) off the UI thread."""

    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self) -> None:  # noqa: D401
        try:
            self.ok.emit(self._fn(*self._args))
        except Exception as exc:  # surfaced in the UI, never swallowed
            self.failed.emit(str(exc) or exc.__class__.__name__)
