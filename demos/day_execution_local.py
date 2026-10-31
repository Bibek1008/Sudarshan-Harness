"""Execution architecture: local backend, tool adapter, and traversal demo.

This direct demonstration needs no model or API key.  It exercises the same
``Tool`` objects that a loop would receive and shows that the local boundary
returns a readable error instead of reading outside its scratch workspace.
"""

from tempfile import TemporaryDirectory

from sudarshan.execution.base import backend_tools
from sudarshan.execution.local import LocalExecutionBackend
from sudarshan.security import Policy


def main() -> None:
    """Create, execute, read, and boundary-check a local scratch program."""
    with TemporaryDirectory(prefix="sudarshan-local-") as scratch:
        backend = LocalExecutionBackend(scratch)
        tools = {tool.name: tool for tool in backend_tools(backend, "local", Policy("yolo"))}
        source = "print('hello from the local backend')\n"
        print(tools["local_write_file"].run("hello.py", source))
        print(tools["local_bash"].run("python hello.py"))
        print(tools["local_read_file"].run("hello.py"))
        print(tools["local_read_file"].run("../../etc/passwd"))


if __name__ == "__main__":
    main()
