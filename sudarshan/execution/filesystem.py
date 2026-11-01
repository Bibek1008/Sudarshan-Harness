"""Handle-based file access shared by local backend and core file tools.

Reject link/reparse traversal, alternate streams and multiply linked files.
Windows directory handles deny rename/delete while the operation is active.
POSIX walks use directory descriptors and O_NOFOLLOW, not check-then-open paths.
Neither mechanism isolates arbitrary shell commands or hostile workspace owners.
"""
from contextlib import contextmanager
import os
from pathlib import Path, PureWindowsPath
import stat

from .base import ExecutionPermissionError

FILE_LIMIT = 1024 * 1024


def parts_for(path):
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ExecutionPermissionError("a nonempty relative file path is required")
    windows = PureWindowsPath(path)
    candidate = Path(path)
    if candidate.is_absolute() or windows.drive or windows.root:
        raise ExecutionPermissionError("absolute and drive-relative paths are not permitted")
    parts = candidate.parts
    if not parts or any(part in ("..", "") for part in parts):
        raise ExecutionPermissionError("file path escapes the working directory")
    if os.name == "nt":
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if any(":" in part or part.endswith((".", " ")) or part.split(".")[0].upper() in reserved for part in parts):
            raise ExecutionPermissionError("Windows streams, devices and ambiguous paths are not permitted")
    return parts


class WorkspaceFiles:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.identity = self.root.stat()

    @contextmanager
    def open(self, path, mode="r"):
        parts = parts_for(path)
        if mode not in {"r", "w", "r+"}:
            raise ValueError("unsupported workspace open mode")
        if os.name == "nt":
            with self._windows(parts, mode) as handle:
                yield handle
        else:
            with self._posix(parts, mode) as handle:
                yield handle

    @contextmanager
    def _posix(self, parts, mode):
        if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            raise ExecutionPermissionError("secure descriptor-relative file access unavailable")
        descriptors = []
        try:
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(directory)
            info = os.fstat(directory)
            if (info.st_dev, info.st_ino) != (self.identity.st_dev, self.identity.st_ino):
                raise ExecutionPermissionError("workspace root identity changed")
            for part in parts[:-1]:
                if mode == "w":
                    try:
                        os.mkdir(part, dir_fd=directory)
                    except FileExistsError:
                        pass
                directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                descriptors.append(directory)
            flags = os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_RDONLY if mode == "r" else os.O_RDWR)
            if mode == "w":
                flags |= os.O_CREAT
            descriptor = os.open(parts[-1], flags, 0o600, dir_fd=directory)
            descriptors.append(descriptor)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ExecutionPermissionError("file must be regular and have a single link")
            if mode == "w":
                os.ftruncate(descriptor, 0)
            with os.fdopen(descriptor, "r" if mode == "r" else "r+", encoding="utf-8", errors="replace") as handle:
                descriptors.pop()
                yield handle
        except OSError as error:
            if error.errno in {40, 20}:  # ELOOP / ENOTDIR
                raise ExecutionPermissionError("link or non-directory file component rejected") from None
            raise
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    @contextmanager
    def _windows(self, parts, mode):
        import ctypes as c
        from ctypes import wintypes as w
        import msvcrt
        kernel = c.WinDLL("kernel32", use_last_error=True)
        class Info(c.Structure):
            _fields_ = [("attributes", w.DWORD), ("creation", w.FILETIME),
                        ("access", w.FILETIME), ("write", w.FILETIME),
                        ("volume", w.DWORD), ("size_high", w.DWORD), ("size_low", w.DWORD),
                        ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]
        kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        kernel.CreateFileW.restype = w.HANDLE
        kernel.GetFileInformationByHandle.argtypes = [w.HANDLE, c.POINTER(Info)]
        kernel.GetFileInformationByHandle.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        handles = []
        descriptor = None
        def acquire(path, directory=False):
            # No FILE_SHARE_DELETE: pinned components cannot be renamed or replaced.
            access = 0x80 if directory else (0x80000000 if mode == "r" else 0xC0000000)
            sharing = 3 if directory else 1
            disposition = 4 if not directory and mode == "w" else 3  # OPEN_ALWAYS / OPEN_EXISTING
            handle = kernel.CreateFileW(str(path), access, sharing, None, disposition,
                                        0x00200000 | (0x02000000 if directory else 0), None)
            if handle == c.c_void_p(-1).value:
                raise c.WinError(c.get_last_error())
            handles.append(handle)
            info = Info()
            if not kernel.GetFileInformationByHandle(handle, c.byref(info)):
                raise c.WinError(c.get_last_error())
            if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory:
                raise ExecutionPermissionError("reparse points and non-regular components are not permitted")
            if not directory and info.links != 1:
                raise ExecutionPermissionError("multiply linked files are not permitted")
            return handle
        try:
            # Pin every ancestor, including root ancestors: a junction/rename above
            # the configured root cannot redirect a later full-path CreateFile.
            current = Path(self.root.anchor)
            acquire(current, directory=True)
            for part in self.root.parts[1:]:
                current = current / part
                acquire(current, directory=True)
            if not os.path.samestat(current.stat(), self.identity):
                raise ExecutionPermissionError("workspace root identity changed")
            for part in parts[:-1]:
                current = current / part
                if mode == "w":
                    current.mkdir(exist_ok=True)
                acquire(current, directory=True)
            final = acquire(current / parts[-1])
            descriptor = msvcrt.open_osfhandle(final, os.O_RDONLY if mode == "r" else os.O_RDWR)
            handles.pop()  # descriptor owns final handle
            if mode == "w":
                os.ftruncate(descriptor, 0)
            with os.fdopen(descriptor, "r" if mode == "r" else "r+", encoding="utf-8", errors="replace") as handle:
                descriptor = None
                yield handle
        finally:
            if descriptor is not None:
                os.close(descriptor)
            for handle in reversed(handles):
                kernel.CloseHandle(handle)

    def read_text(self, path):
        with self.open(path) as handle:
            text = handle.read(FILE_LIMIT + 1)
            if len(text) > FILE_LIMIT:
                raise ValueError("file exceeds workspace text limit")
            return text

    def write_text(self, path, content):
        if len(content) > FILE_LIMIT:
            raise ValueError("content exceeds workspace text limit")
        with self.open(path, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
