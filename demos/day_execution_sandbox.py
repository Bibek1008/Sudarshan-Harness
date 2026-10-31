"""Execution architecture: Docker sandbox success, timeout, and absence paths.

The backend uses Docker only when it is installed.  A Docker container narrows
risk but is not an absolute security boundary; this demo never presents a
normal subprocess as a sandbox and catches unavailable-runtime failures.
"""

from tempfile import TemporaryDirectory

from sudarshan.execution.base import BackendUnavailable, ExecutionTimeout
from sudarshan.execution.sandbox import SandboxedExecutionBackend


def main() -> None:
    """Run a harmless container command and demonstrate its failure modes."""
    with TemporaryDirectory(prefix="sudarshan-sandbox-") as scratch:
        backend = SandboxedExecutionBackend(scratch)
        try:
            print(backend.execute("python -c \"print('hello from sandbox')\"").text())
            try:
                backend.execute("sleep 5", timeout=0.1)
            except ExecutionTimeout as error:
                print(f"timeout demonstration: {error}")
        except BackendUnavailable as error:
            print(f"unavailable-runtime demonstration: {error}")


if __name__ == "__main__":
    main()
