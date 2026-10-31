"""Minimal inherited environment for local shell processes.

Only executable lookup, Windows runtime and temporary-directory variables pass
through. Credentials, HOME/USERPROFILE, shell startup hooks, Python injection
variables and agent sockets are excluded by default, including unknown names.
Allowed values and executable search paths must come from a trusted host.
This limits environment inheritance; it does not isolate filesystem access.
"""

import os


SHELL_ENVIRONMENT_ALLOWLIST = frozenset({
    "COMSPEC", "PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR",
})


def safe_shell_environment() -> dict[str, str]:
    """Return a fresh allowlisted copy without mutating the provider environment."""
    return {key: value for key, value in os.environ.items()
            if key.upper() in SHELL_ENVIRONMENT_ALLOWLIST}
