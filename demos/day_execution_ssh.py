"""Execution architecture: explicit SSH configuration and failure reporting.

No remote connection is attempted unless the caller supplies ``--host``.
The demo uses the system SSH client, preserves strict host-key verification,
and reports ordinary authentication or connection failures as structured data.
"""

import argparse

from sudarshan.execution.base import ExecutionError
from sudarshan.execution.remote import RemoteExecutionBackend


def main() -> None:
    """Run harmless remote command and read examples with caller-supplied settings."""
    parser = argparse.ArgumentParser(description="Run Sudarshan's SSH backend demo.")
    parser.add_argument("--host", help="SSH host; omit to demonstrate configuration without connecting.")
    parser.add_argument("--user", help="SSH username, using SSH config when omitted.")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22).")
    parser.add_argument("--identity-file", help="Optional SSH private-key path.")
    parser.add_argument("--workdir", default=".", help="Remote workspace root.")
    parser.add_argument("--path", default="README.md", help="Remote workspace-relative file to read.")
    args = parser.parse_args()
    if not args.host:
        print("No host supplied. Pass --host, --user, and --workdir to make an SSH request.")
        return
    backend = RemoteExecutionBackend(
        args.host, username=args.user, port=args.port,
        identity_file=args.identity_file, workdir=args.workdir,
    )
    try:
        print(backend.execute("printf 'hello from Sudarshan SSH\\n'").text())
        print(backend.read_file(args.path).text())
    except ExecutionError as error:
        print(f"SSH demo could not run: {type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
