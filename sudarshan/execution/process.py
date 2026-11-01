"""Owned process-tree lifecycle; this is not filesystem/network isolation."""
import shutil
from pathlib import Path

import math
import os
import signal
import subprocess
import sys
import threading
import time

from ..environment import safe_shell_environment
from ..redaction import redact
from .base import ExecutionError, ExecutionTimeout

OUTPUT_BUDGET = 1024 * 1024
CAPTURE_LIMIT = 12000


def validate_timeout(timeout):
    try:
        value = float(timeout)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("timeout must be a finite number between 0 and 3600 seconds") from None
    if not math.isfinite(value) or not 0 < value <= 3600:
        raise ValueError("timeout must be a finite number between 0 and 3600 seconds")
    return value


class WindowsJob:
    """A non-inheritable Job Object: descendants cannot opt out of ownership."""
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c = c
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        class Basic(c.Structure):
            _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64),
                        ("flags", w.DWORD), ("minimum", c.c_size_t),
                        ("maximum", c.c_size_t), ("active", w.DWORD),
                        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(c.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", c.c_size_t),
                        ("job_memory", c.c_size_t), ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]
        self.kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.kernel.SetInformationJobObject.restype = w.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = w.BOOL
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CloseHandle.restype = w.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ExecutionError("cannot create process Job Object")
        limits = Extended()
        limits.basic.flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS
        limits.basic.active = 64
        if not self.kernel.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)):
            self.close()
            raise ExecutionError("cannot configure process Job Object")

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ExecutionError("cannot assign process Job Object; command was not started")

    def close(self):
        if self.handle:
            if not self.kernel.CloseHandle(self.handle):
                raise ExecutionError("cannot close process Job Object; cleanup unconfirmed")
            self.handle = None


# The wrapper cannot launch the command until its parent assigns the Job Object.
# -I -S avoids workspace imports, user site code and PYTHON* startup hooks.
_GATE = r"""import json, subprocess, sys
args, shell = json.loads(sys.argv[1])
if sys.stdin.buffer.readline() != b'go\n':
    raise SystemExit(125)
raise SystemExit(subprocess.call(args, shell=shell, stdin=subprocess.DEVNULL))
"""


def _environment():
    env = safe_shell_environment()
    if os.name == "nt":
        import ctypes as c
        from ctypes import wintypes as w
        kernel = c.WinDLL("kernel32", use_last_error=True)
        kernel.GetSystemDirectoryW.argtypes = [w.LPWSTR, w.UINT]
        kernel.GetSystemDirectoryW.restype = w.UINT
        buffer = c.create_unicode_buffer(32768)
        size = kernel.GetSystemDirectoryW(buffer, len(buffer))
        if not size or size >= len(buffer):
            raise ExecutionError("cannot locate trusted Windows command interpreter")
        env["COMSPEC"] = os.path.join(buffer.value, "cmd.exe")
    return env


def run_owned(command, *, cwd=None, timeout=120, shell=False):
    """Run with filtered environment, bounded capture and owned-tree cleanup.

    Windows commands are gated until Job assignment. POSIX commands start a new
    process group. POSIX descendants that deliberately create new sessions escape
    group cleanup; use a cgroup/container for adversarial process isolation.
    """
    import json
    timeout = validate_timeout(timeout)
    if shell and (not isinstance(command, str) or not command.strip() or "\x00" in command):
        raise ValueError("command must be nonempty text without NUL")
    job = WindowsJob() if os.name == "nt" else None
    process = None
    readers = []
    overflow = threading.Event()
    read_error = threading.Event()
    captures = [bytearray(), bytearray()]
    totals = [0, 0]
    started = time.monotonic()

    def drain(pipe, index):
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    return
                totals[index] += len(chunk)
                if totals[index] > OUTPUT_BUDGET:
                    overflow.set()
                captures[index].extend(chunk)
                if len(captures[index]) > CAPTURE_LIMIT:
                    del captures[index][CAPTURE_LIMIT // 2:-CAPTURE_LIMIT // 2]
        except Exception:
            # Reader failures must not create background-thread tracebacks.
            read_error.set()

    try:
        args = [sys.executable, "-I", "-S", "-c", _GATE, json.dumps([command, shell])] if job else command
        process = subprocess.Popen(args, shell=False if job else shell, cwd=cwd,
                                   env=_environment(), stdin=subprocess.PIPE if job else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=not bool(job), close_fds=True)
        if job:
            job.assign(process)
            process.stdin.write(b"go\n")
            process.stdin.flush()
            process.stdin.close()
        for index, pipe in enumerate((process.stdout, process.stderr)):
            thread = threading.Thread(target=drain, args=(pipe, index), daemon=True)
            thread.start()
            readers.append(thread)
        while process.poll() is None:
            if overflow.is_set():
                raise ExecutionError("command exceeded output budget")
            if read_error.is_set():
                raise ExecutionError("command output capture failed")
            if time.monotonic() - started >= timeout:
                raise ExecutionTimeout(f"command timed out after {timeout:g}s")
            time.sleep(0.01)
    except (OSError, subprocess.SubprocessError):
        raise ExecutionError("could not run owned process") from None
    finally:
        # Run for success, timeout, failed setup and BaseException/interrupt alike.
        try:
            if job:
                job.close()
            elif process:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        finally:
            if process:
                try:
                    if process.poll() is None:
                        process.kill()  # setup failed before ownership was established
                    process.wait(timeout=5)
                except (OSError, subprocess.SubprocessError):
                    raise ExecutionError("process cleanup failed; descendant cleanup unconfirmed") from None
                finally:
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                    for thread in readers:
                        thread.join(timeout=5)
                    if any(thread.is_alive() for thread in readers):
                        raise ExecutionError("output pipes remain open; descendant cleanup unconfirmed")
                    for pipe in (process.stdout, process.stderr):
                        pipe.close()
    if overflow.is_set():
        raise ExecutionError("command exceeded output budget")
    if read_error.is_set():
        raise ExecutionError("command output capture failed")
    output = [redact(bytes(value).decode("utf-8", errors="replace")) for value in captures]
    for index in range(2):
        if totals[index] > CAPTURE_LIMIT:
            middle = CAPTURE_LIMIT // 2
            output[index] = output[index][:middle] + "\n... output truncated ...\n" + output[index][middle:]
    return subprocess.CompletedProcess(command, process.returncode, *output)


def trusted_executable(name, workspace):
    """Resolve backend clients using absolute PATH entries, never implicit cwd.

    Host PATH directories/configuration must still be trusted. Windows batch
    scripts are excluded because the OS can interpret their arguments via cmd.
    """
    root = Path(workspace).resolve()
    requested = Path(name)
    candidates = [requested] if requested.is_absolute() else [
        Path(entry) / requested for entry in os.get_exec_path()
        if entry and Path(entry).is_absolute()]
    for candidate in candidates:
        # Absolute operands prevent shutil.which's implicit Windows cwd search.
        found = shutil.which(str(candidate))
        if not found:
            continue
        target = Path(found).resolve()
        if target.is_relative_to(root):
            continue
        if os.name == "nt" and target.suffix.lower() != ".exe":
            continue
        return str(target)
    return None
