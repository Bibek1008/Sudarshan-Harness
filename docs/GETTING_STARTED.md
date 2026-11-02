# Getting started

Sudarshan is a personal Python coding-agent harness. The easiest way to use it
is to install the wheel from the [GitHub Releases page](https://github.com/Bibek1008/Sudarshan-Harness/releases).
Python 3.10 or newer is required. The package has no third-party runtime
dependencies.

## Install once

Download the `sudarshan_harness-<version>-py3-none-any.whl` asset from a release,
then install it in the Python environment you plan to use:

```powershell
python --version
python -m pip install --upgrade .\sudarshan_harness-<version>-py3-none-any.whl
sudarshan --help
sudarshan benchmark list
```

Use the same Python interpreter to install and run Sudarshan. The command is
available from any working directory while that environment is active. See
[package installation](PACKAGING.md) for the full PowerShell workflow and
upgrade instructions.

## Configure Gemini

Set the API key in the environment of the terminal where you will run
Sudarshan. The provider checks `SUDARSHAN_API_KEY`, then legacy
`ODYSSEUS_API_KEY`, then `GEMINI_API_KEY`. Sudarshan does not automatically
read `.env` files.

For example, in PowerShell:

```powershell
$env:SUDARSHAN_API_KEY = "YOUR_GEMINI_API_KEY"
```

Replace the placeholder locally; do not commit the value, put it in source code,
or include it in task prompts. The variable remains in that PowerShell process
until it exits or you remove it. A masked prompt version is documented in
[package installation](PACKAGING.md).

The default model is `gemini-3.1-pro-preview`. Override it with `-m MODEL` or
`ODYSSEUS_MODEL`. Model access and API usage depend on your Gemini account.
Help, package installation, benchmark listing, and benchmark dry-runs do not
make Gemini requests.

## Work on a project

Move to the application directory. Sudarshan is already installed, so there is
no need to clone or copy the harness into each application:

```powershell
Set-Location C:\path\to\my-project
sudarshan -d . --mode safe
```

Or give it one task:

```powershell
sudarshan -d . --mode safe -p "Inspect this project and explain its structure."
```

The current directory is the project root. Keep using the same `-d` directory
when returning to the project. Its memory and runtime state are stored there,
not globally.

The CLI and `Harness()` default to `safe`. Non-read actions require explicit
approval; review the proposed tool and arguments before answering `y` or
`yes`. Blank input and EOF refuse. `read-only` is useful for initial
inspection. `yolo` skips approvals but remains subject to hard-deny checks and
is not an OS sandbox. It is not needed for ordinary first use.

A project directory is not a security boundary: shell commands run with your
Windows account's permissions. Use trusted workspaces, inspect proposed
commands, and read the [security overview](SECURITY.md) before running code
you do not trust. For untrusted generated programs, use separately verified
OS isolation.

## Project memory, sessions and skills

Each project can have an editable `SUDARSHAN.md` for durable project facts.
Memory is bounded and project-local; it is not shared automatically between
separate applications. The model only saves facts when the memory tool is
explicitly requested and its tool call is approved. Do not save credentials or
personal data.

Transcripts and telemetry are stored below the project's `.sudarshan/`
directory. Transcripts may contain task text, tool arguments and outputs, so
keep them private. Disabling telemetry does not disable transcript persistence.

Resume a session from the same project root:

```powershell
sudarshan -d . --resume
```

Project skills are optional Markdown files under
`skills/<skill-name>/SKILL.md` in the project itself. They are not installed
globally by the wheel. The ordinary agent tools, memory, sessions, telemetry,
and benchmark CLI work without additional skills.

## Diagnostics and benchmarks

```powershell
sudarshan stats -d . --json
sudarshan benchmark list
sudarshan benchmark run core --dry-run
```

The wheel includes the versioned benchmark definitions, fixtures and
independent verifiers. Dry-run validates configuration and reports zero model
requests. Live benchmarks require explicit `--live --model MODEL` and consume
Gemini quota or money.

## Work on Sudarshan itself

The installable package is for using the harness. To modify its source or run
the complete developer test suite, clone the repository separately:

```powershell
git clone https://github.com/Bibek1008/Sudarshan-Harness.git
Set-Location .\Sudarshan-Harness
python -m unittest discover -v
python -m sudarshan --help
```

The complete test suite and demos are kept in the source repository; they are
not installed into each project environment.
