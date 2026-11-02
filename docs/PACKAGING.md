# Install Sudarshan as a Python package

Sudarshan can be installed once into a Python environment and then launched
from any application directory. The package has no third-party runtime
dependencies. Python 3.10 or newer is required.

## 1. Download the package

Open the [GitHub Releases page](https://github.com/Bibek1008/Sudarshan-Harness/releases)
and download the wheel asset named like:

```text
sudarshan_harness-1.0.1-py3-none-any.whl
```

The wheel is a portable Python package; it is not a Windows executable.
The matching source archive is also attached for inspection.

## 2. Install it once

In PowerShell, change to the directory where the wheel was downloaded and run:

```powershell
python --version
python -m pip install --upgrade .\sudarshan_harness-1.0.1-py3-none-any.whl
```

Use the same `python` interpreter when installing and running Sudarshan.
The install is per Python environment. A normal system Python environment
makes the command available from other folders using that interpreter; a
virtual environment makes it available while that environment is activated.

Check the command:

```powershell
sudarshan --help
sudarshan benchmark list
```

The package includes the benchmark manifests, fixtures, and verifier files,
so the benchmark CLI remains available after installation. It does not bundle
the repository's tests, demos, or optional project skills.

## 3. Configure your Gemini API key

Sudarshan reads the API key from the process environment first, checking these
names in order:

1. `SUDARSHAN_API_KEY`
2. `ODYSSEUS_API_KEY` (legacy compatibility)
3. `GEMINI_API_KEY`

When none of those variables is set, Sudarshan reads the same names from a
project-local `.env` file. The file is read from the directory supplied with
`-d` (the current directory when `-d` is omitted). Create `.env` in your
application's project root:

```dotenv
SUDARSHAN_API_KEY=your-gemini-api-key
```

A quoted value is also accepted. Only these three API-key entries are read;
the file is not executed, shell commands and variable interpolation are not
supported, and unrelated settings are ignored. Process environment variables
take precedence over every value in `.env`.

The repository's `.gitignore` excludes `.env` files. Keep your own project
ignore rules in place too, and never commit a real key, put it in source code,
or paste it into an agent task. Sudarshan reads the key directly for provider
requests; it does not add the key to the process environment, transcripts,
telemetry, or child shell-command environments.

For a masked PowerShell prompt instead of a `.env` file, see the environment
variable example below:

```powershell
$secureKey = Read-Host "Gemini API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $env:SUDARSHAN_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    $secureKey.Dispose()
}
```

The environment variable remains available in that PowerShell process until
you close it or clear it with `Remove-Item Env:SUDARSHAN_API_KEY`. It is not
written into the application folder.

Select a model with `-m MODEL` or set `ODYSSEUS_MODEL` in the process
environment. The provider default is `gemini-3.1-pro-preview`; model access
and API quota depend on your Gemini account. Installing the wheel and running
`--help` do not make API requests.

## 4. Start a new application

Create or open a separate folder for the application. Do not build the
application inside the Sudarshan source repository.

```powershell
New-Item -ItemType Directory -Force C:\Users\User\Desktop\MyProjects\expense-tracker
Set-Location C:\Users\User\Desktop\MyProjects\expense-tracker

# Create .env in this folder and add SUDARSHAN_API_KEY before starting.
notepad .env

# Start an interactive coding session
sudarshan -d . --mode safe
```

Or give it one task:

```powershell
sudarshan -d . --mode safe -p "Inspect this project and propose a small implementation plan."
```

The current directory is the project root. Sudarshan stores that project's
sessions, telemetry, and `SUDARSHAN.md` memory under that project. Use the same
`-d` directory when returning to the project so its memory and sessions remain
associated with it.

The default `safe` mode asks before actions that can change files or run
commands. Review each proposed action before approving it. `read-only` is useful
for initial inspection. `yolo` skips approvals and is not an OS sandbox; it is
not recommended for ordinary first use. A project directory is not a security
boundary: shell commands run with your Windows account's permissions.

## 5. Use Sudarshan in another project

Move to that project's directory, add its own `.env` file, and run the same
installed command:

```powershell
Set-Location C:\Users\User\Desktop\MyProjects\another-app
notepad .env
sudarshan -d . --mode safe
```

Each project gets its own memory, session data, and optional API key. You do
not need to clone Sudarshan again, and you should not copy its Python source
into every project.

Project skills are optional Markdown files stored in a project's own
`skills/<skill-name>/SKILL.md` directory. They are not installed globally by
the wheel. The regular agent tools, memory, sessions, and benchmark command
work without project skills.

## 6. Upgrade later

Download the newer wheel from the next GitHub Release and install it with:

```powershell
python -m pip install --upgrade .\sudarshan_harness-NEW_VERSION-py3-none-any.whl
```

No API key is included in the package or release asset.
