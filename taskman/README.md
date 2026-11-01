# Task Manager CLI

Taskman is a Python task manager with no external dependencies. Use Python 3.9+
from this project directory.

## Commands

```console
python -m taskman --help
python -m taskman add "Buy groceries" "Milk and fresh bread"
python -m taskman add "Plan trip" Research train tickets
python -m taskman list
python -m taskman complete <id>
python -m taskman show <id>
python -m taskman delete <id>
python -m taskman add --help
```

Replace `<id>` with the exact ID printed by add or list. New tasks use full UUIDs;
existing short IDs remain supported. Quote titles containing spaces. Descriptions
may be quoted or provided as several words, which are joined with spaces. Use `--`
before positional values beginning with a hyphen.

## Storage and errors

Tasks are stored as UTF-8 JSON in `tasks.json` in the current working directory.
Run from the same directory to access the same tasks across processes. A missing
file means no tasks yet. Empty or whitespace-only titles are rejected.
Malformed JSON, invalid records, duplicate IDs, and unreadable files produce an
error; the original storage is preserved and the command stops. Back up and repair
invalid storage manually before retrying. Task records require text ID, title,
description, ISO timestamp `created_at`, and boolean `completed` fields.

Writes use a unique temporary file in the storage directory, flush and sync its
contents, then atomically replace the destination. Failed writes attempt to remove
the temporary file and report cleanup failures. Concurrent writers are not locked;
use one writer at a time. Atomic replacement does not guarantee directory metadata
survives a power loss.

Success and help exit with code 0. Storage errors, invalid titles, and missing task
IDs exit with code 1. Missing arguments and unknown commands exit with code 2.
Expected errors are printed to stderr without tracebacks.

## Testing

```console
python -m unittest discover -s tests -v
```

Tests use isolated `tempfile.TemporaryDirectory` storage under `tests/`, including
fresh-process CLI checks. They do not read or change your existing `tasks.json`.
