# KITSUMA

A college-level **hierarchy-based mini-git** for collaborating on text files.
Create a project, assign employees to folders, submit changes through an ordered
review hierarchy, and let the folder head merge the accepted version.

**Stack:** C++17, Python 3.10+, PostgreSQL, and `psycopg2`. The application runs in
the terminal. C++ implements the Myers-diff three-way merge tool; Python handles
commands, accounts, workspaces, database operations, and hierarchy rules.

## Features

- Project creation with admin accounts, employee accounts, and folder assignments.
- Ranked review routing and a final folder-head merge, with an admin override.
- Clone assigned files into separate employee working directories.
- Submit selected files or all modified tracked files with a commit message.
- Three-way merging using the original base, submitted content, and shared version.
- Inspect pending changes, view accepted revisions, and pull shared updates.
- Protect local edits from accidental replacement.

## Quick start: automatic demo

Open PowerShell in the repository directory. Install Python 3.10+, `g++` with
C++17 support, and PostgreSQL including `initdb` and `pg_ctl` if needed.

```powershell
python -m pip install -r requirements.txt
python scripts/test_local.py --demo
```

This builds the C++ executables, runs the randomized merge checks and Python
tests, then demonstrates two employees submitting conflicting changes. It starts
a disposable PostgreSQL server bound to localhost on a temporary port and stops
and deletes that temporary database afterward. It does not use your configured
database, `.env`, Render, or Supabase. No cloud account is needed.

A successful run ends with `DEMO PASSED`. Demo data is temporary; use the setup
below for projects you want to keep. Demo output is printed to the terminal rather
than saved as another project file.

On Windows, the script discovers PostgreSQL in `Program Files/PostgreSQL` or on
PATH. If discovery fails, set the installed binary directory, for example:

```powershell
$env:PG_BIN = "C:\Program Files\PostgreSQL\18\bin"
```

On Linux/macOS, put the PostgreSQL binaries on PATH or set `PG_BIN`. Run the local
database tests as a normal user; PostgreSQL cannot run as root.

## Setup for persistent projects

### 1. Install dependencies and build

```powershell
python -m pip install -r requirements.txt
python build.py
```

The build produces `build/kitsuma.exe` and `build/update.exe` on Windows. Rebuild
after editing C++ source. Set `CXX` if your compiler executable is not `g++`.

The remaining examples use PowerShell. On Linux/macOS, use `./build/kitsuma`
instead of `.\build\kitsuma.exe`. Every application command is also available
as `python load.py <command>`, but interactive conflict resolution still requires
the compiled C++ merge tool.

### 2. Configure PostgreSQL

Use a fresh local database or a fresh Supabase project. To use local PostgreSQL,
start its server and create a database named `kitsuma` in pgAdmin, or run this
when `createdb` is on PATH:

```powershell
createdb -U postgres kitsuma
```

Copy the configuration template once, preserving any existing configuration:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set your own connection URI:

```dotenv
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/kitsuma
```

The local PostgreSQL password is the password you set for that local server; it
is separate from the old Render account and KITSUMA employee passwords.
Environment variables take precedence over values in `.env`.

For **Supabase**, copy the PostgreSQL **session pooler** URI from the project's
Connect dialog, replace the password placeholder, and include `sslmode=require`.
URL-encode special characters in the database password. Use the database owner
role. See [Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).

Supabase Auth is not used. KITSUMA keeps its own hashed passwords and sessions.
The schema enables row-level security without public API policies to keep these
tables out of the public Data API; the owner-connected CLI still accesses them.

### 3. Initialize the schema

```powershell
.\build\kitsuma.exe db-init
```

This creates the tables and the `pgcrypto` extension. It is safe to rerun on this
version's schema. It refuses the incompatible old prototype schema rather than
overwriting it. Export any Render data you want to keep and recreate the demo in
a fresh database; automatic import of old records is not implemented. No hosted
database is provisioned or migrated by these commands.

### 4. Create a project

For an interactive form:

```powershell
.\build\kitsuma.exe init
```

Or create the supplied example, which includes initial file contents:

```powershell
.\build\kitsuma.exe init --spec examples/project.json
```

Choose a password for each account when prompted. The example creates
`MusicPlayer`, with `admin@MusicPlayer`, `alice@MusicPlayer`, `bob@MusicPlayer`,
and `head@MusicPlayer`. The admin is logged in after creation. Interactive setup
creates empty files; JSON specifications can supply initial contents. Do not put
passwords in the JSON specification.

Project and account names use letters, numbers, `_`, and `-`. Folder/file paths
use `/` separators; nested directories, dotted folder names, extensionless files,
and spaces in file paths are supported. Hierarchies are assigned to top-level
folders. Root-level files are admin-only. An employee can belong to or head
several folders. A folder's hierarchy must contain distinct employees and end
with its head.

## Hierarchy and submission lifecycle

The sample `src` hierarchy is:

```text
alice (rank 1) -> bob (rank 2) -> head (rank 3)
```

1. Alice submits a changed file. Its shared version remains unchanged.
2. Bob inspects the change with `show` and approves it with `review`.
3. The submission moves to Head, who merges it into the shared version.
4. Employees pull the accepted result into their own working directories.

Bob's own submissions go directly to Head. Head's submissions go to Admin.
Admin can merge any pending submission as an override; Admin's own submissions
are assigned to Admin. Intermediate approvals forward the content unchanged.

Each submitted file records its author, message, reviewer, original revision,
and original content. The final merge compares that **base** against **A: the
submission** and **B: the current shared version**. Accepted content, revision
history, and merged status are saved together. If another merge changes the
shared revision during interactive resolution, saving stops and asks you to retry.

Multiple submissions may be pending, but each file is merged separately, one
submission at a time. An author can have only one pending submission per file.

## Manual walkthrough: two conflicting edits

After creating the sample project, clone both working copies before making edits:

```powershell
.\build\kitsuma.exe login alice@MusicPlayer
.\build\kitsuma.exe clone MusicPlayer workspaces/alice
.\build\kitsuma.exe login bob@MusicPlayer
.\build\kitsuma.exe clone MusicPlayer workspaces/bob
```

Change the first line of Alice's `src/player.txt` to `volume = 20` and Bob's copy
to `volume = 30`. Their common base is `volume = 10`.

Submit Alice's file, then inspect and approve it as Bob:

```powershell
.\build\kitsuma.exe login alice@MusicPlayer
.\build\kitsuma.exe status --workspace workspaces/alice
.\build\kitsuma.exe add src/player.txt -m "Alice changes volume" --workspace workspaces/alice
.\build\kitsuma.exe login bob@MusicPlayer
.\build\kitsuma.exe pending MusicPlayer
.\build\kitsuma.exe show 1
.\build\kitsuma.exe review 1
```

**Replace `1` with Alice's actual submission ID** printed by `add` or `pending`.
Then submit Bob's changes and merge both submissions as Head:

```powershell
.\build\kitsuma.exe add . -m "Bob changes volume" --workspace workspaces/bob
.\build\kitsuma.exe login head@MusicPlayer
.\build\kitsuma.exe pending MusicPlayer
.\build\kitsuma.exe merge 1
.\build\kitsuma.exe merge 2
```

Replace both IDs with the actual IDs. The first merge accepts Alice's version.
The second detects the conflicting volume change and opens the C++ resolver.

| Choice | Result |
| --- | --- |
| `a` | Keep submitted content: Bob's volume 30 |
| `b` | Keep current shared content: Alice's volume 20 |
| `ab` / `ba` | Keep both versions in the selected order |
| `e` | Enter custom lines; a single `.` ends input, blank lines are allowed |
| `s` | Drop both conflicting sections |

Automatic changes ask for `y` to accept or `n` to override. Closing input cancels
the unresolved merge without saving it. Choose `a` to follow the rest of this
example, then download the result:

```powershell
.\build\kitsuma.exe log MusicPlayer
.\build\kitsuma.exe login bob@MusicPlayer
.\build\kitsuma.exe pull --workspace workspaces/bob
.\build\kitsuma.exe login alice@MusicPlayer
.\build\kitsuma.exe pull --workspace workspaces/alice --discard-local
.\build\kitsuma.exe status --workspace workspaces/alice
```

Both copies now contain volume 30. Ordinary `pull` protects local edits.
`--discard-local` explicitly replaces local content with the shared version; save
any other local work first. Alice needs it here because her volume 20 differs
from the final resolution. `status` compares against the last clone/pull base, so
submissions remain locally modified until pulled. Only one login is active at a
time; logging in as someone else does not change an existing workspace's owner.

## Command reference

| Command | Purpose |
| --- | --- |
| `db-init` | Initialize a fresh PostgreSQL database |
| `init [--spec file.json]` | Create a project and its accounts, files, and hierarchy |
| `menu` | Open the interactive create-project/login prompt |
| `login user@project` / `logout` | Set or clear the active session |
| `clone project directory` | Download assigned files into an empty directory |
| `status --workspace directory` | List clean, modified, or missing tracked files |
| `add path... -m "message" --workspace directory` | Submit selected tracked paths; `.` selects all changed files |
| `pending project` | List your authored/assigned pending submissions; admin sees all |
| `show id` | Inspect a submission before review |
| `review id` | Approve and forward to the next ranked employee |
| `merge id` | Save the shared result as the assigned head or admin |
| `pull --workspace directory [--discard-local]` | Download shared versions and refresh local bases |
| `log project` | Display accepted per-file revisions |

Use `.\build\kitsuma.exe --help` or append `--help` to a command for its arguments.
`kitsuma.exe` is the single application entry point; the old `run`, `define`, and
`add` executable aliases have been removed.

The merge tool can also run independently:

```powershell
.\build\update.exe base.txt submitted.txt current.txt resolved.txt
```

All four paths are required. Inputs must exist; the output path must be new.
The application normally supplies private temporary files automatically.

## Code organization

```text
KITSUMA/
|-- kitsuma.cpp             # C++ application launcher
|-- cli_bridge.hpp          # Launch Python safely, including Windows argument quoting
|-- update.cpp              # Myers diff and interactive three-way merge
|-- load.py                 # Python application entry point
|-- kitsuma/
|   |-- __init__.py
|   |-- cli.py              # Commands, forms, and console output
|   |-- core.py             # Workspace, submission, hierarchy, and merge rules
|   `-- db.py               # Configuration and schema initialization
|-- kitsumadb.sql           # PostgreSQL schema, relationships, and access settings
|-- build.py                # Build the two C++ executables
|-- requirements.txt        # Python dependency
|-- .env.example            # Database configuration template
|-- examples/project.json  # Sample project with initial content
|-- scripts/
|   |-- test_local.py       # Disposable PostgreSQL tests and optional demo
|   `-- demo.py             # Automatic two-employee scenario
`-- tests/
    |-- merge_tests.cpp     # Randomized diff/merge and targeted conflict checks
    `-- test_project.py     # Validation, C++ process, and PostgreSQL workflow tests
```

`build/`, Python caches, `.env`, `.kitsuma/`, and `workspaces/` are generated or
local-only and ignored by Git. The optional `.vscode/` folder contains personal
editor settings and is also ignored.

The main refactor replaced shared temporary text files and duplicated setup code
with Python modules and per-workspace JSON metadata. Database transactions keep
related writes together; constraints prevent duplicate assignments; session
tokens identify logged-in users; retained base snapshots make merges reproducible.
Myers diff remains in C++. Build-once executables and direct subprocess arguments
replace runtime compilation and user-built shell commands.

## Tests

```powershell
python scripts/test_local.py          # Build and run all tests with temporary PostgreSQL
python scripts/test_local.py --demo   # Also execute the complete demo
```

The suite includes 10,000 randomized diff/merge cases, delete-versus-edit checks,
empty/missing input and cancelled merge checks, single/all-file submissions,
hierarchy forwarding, folder permissions, project isolation, rollback, local-edit
protection, Windows paths containing spaces, and revision-change detection.

For a fast run without starting PostgreSQL:

```powershell
python build.py
python -m unittest discover -s tests -v
```

Database tests are skipped unless `KITSUMA_TEST_DATABASE_URL` is set. If you set
it manually, use a dedicated test database: tests create/drop their own random
schemas and may install `pgcrypto`. They do not truncate existing project tables.
`scripts/demo.py` alone uses `DATABASE_URL` and creates a new demo project there;
use `test_local.py --demo` when you want everything to be disposable.

## Troubleshooting

- **Compiler not found:** put `g++` on PATH or set `CXX` to its executable path.
- **Python/dependency not found from C++:** install requirements in the intended
  interpreter and set `KITSUMA_PYTHON` to that interpreter's executable path.
- **Database connection fails:** check that PostgreSQL is running and that the
  host, port, username, database name, and password in `DATABASE_URL` are correct.
- **Updated `.env` seems ignored:** an existing `DATABASE_URL` environment variable
  takes precedence. Update or unset that variable in your shell.
- **Old prototype database detected:** use a fresh database and run `db-init`.
- **Project/account already exists:** use its existing login or choose a new
  project name. Re-running `init` does not reset an existing project.
- **Not the current reviewer:** inspect `pending`; intermediate employees use
  `review`, and the assigned head/admin uses `merge`.
- **Pending submission already exists:** finish it before submitting that file again.
- **Pull refuses local edits:** finish the merge, preserve extra edits, then use
  `--discard-local` only if you intend to replace the local content.

## Scope and limits

This is a trusted college CLI project: installations need database credentials.
It is not a public client/server service. Passwords are hashed, local session
tokens expire after 14 days, and credentials/session files are ignored by Git.
Rotate the original committed Render credential if it is still active; deleting
it from current source does not remove it from Git history.

Only UTF-8 text files registered during project creation are tracked. New tracked
files after setup, file rename/delete, binary versioning, arbitrary Git branches,
and automatic legacy-data migration are not implemented. Multi-file submissions
are saved together, but files are reviewed and merged separately. The hierarchy
supports ordered approvals followed by individual three-way merges, not a
simultaneous N-way merge.
