# Environment Notes

Machine: MacBook Air, Apple Silicon (arm64), macOS, zsh
Author: Vicente Alfonso Enrique B.

## Attempt 1 — Python 3.14.2 (FAILED)

The first virtual environment was built on the system interpreter,
Python 3.14.2, which was the only Python available on this machine.

Commands run:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip     # succeeded, pip 26.2.1
    pip install -r requirements.txt          # FAILED

`pip` found no matching wheels for the pinned versions and fell back to
downloading source distributions (`.tar.gz`) for both `pandas` and
`pyarrow`. `pandas` completed metadata preparation from source.
`pyarrow` then failed during `Getting requirements to build wheel`,
which aborted the install before `pandas` reached its compile step:

    error: subprocess-exited-with-error
    x Getting requirements to build wheel did not run successfully.
      exit code: 1
      File "<string>", line 34, in <module>
          ModuleNotFoundError: No module named 'pkg_resources'
    ERROR: Failed to build 'pyarrow' when getting requirements to build wheel

### Diagnosis

This is an interpreter mismatch, not a broken pin. Four of the five
pinned packages were released before Python 3.14 existed, so PyPI
publishes no `cp314` wheel for them on macOS arm64:

| Package                | cp314 wheel | Notes                            |
|------------------------|-------------|----------------------------------|
| pandas==2.2.3          | no          | falls back to source build       |
| pyarrow==17.0.0        | no          | source build requires Arrow C++  |
| psycopg[binary]==3.2.3 | no          | binary distribution, no cp314    |
| python-dotenv==1.0.1   | n/a         | pure Python, installs anywhere   |
| PyYAML==6.0.2          | no          | source build requires Cython     |

Only `pyarrow` was observed to fail. `pandas` was still resolving when
pip aborted, so its source build was never attempted. The wheel
availability above is stated from the distributions pip selected, not
from an observed failure of each package.

Building `pyarrow` from source requires the Apache Arrow C++ libraries
and a configured toolchain, which is out of scope for this activity.

### Decision

Install Python 3.12 via Homebrew and rebuild the virtual environment on
it, keeping `requirements.txt` exactly as provided.

Rationale: the pinned versions are part of the deliverable. Bumping
`pandas` and `pyarrow` to versions with 3.14 wheels would silently change
the library versions that produce the Goal 3 storage benchmark numbers,
which defeats the purpose of a pinned, reproducible environment. Changing
the interpreter to match the pins preserves reproducibility; changing the
pins to match the interpreter does not.

Rejected alternative: `pip install --upgrade setuptools wheel` would
likely clear the `pkg_resources` error, but `pyarrow` would still fail
at the C++ build step, so it does not address the actual cause.

## Attempt 2 — Python 3.12.14 (SUCCESS)

Python 3.12 was installed via Homebrew. Homebrew installs `python@3.12`
as keg-only, so it is not placed on `PATH` and must be invoked by full
path when creating the virtual environment.

Commands run:

    brew install python@3.12
    /opt/homebrew/bin/python3.12 --version    # Python 3.12.14
    deactivate
    rm -rf .venv
    /opt/homebrew/bin/python3.12 -m venv .venv
    source .venv/bin/activate
    python --version                          # Python 3.12.14
    python -m pip install --upgrade pip       # pip 26.2.1
    pip install -r requirements.txt           # SUCCESS

All packages resolved to prebuilt wheels
(`cp312-cp312-macosx_11_0_arm64.whl`). Nothing was compiled from source.

### Recorded environment

Interpreter: Python 3.12.14 (Homebrew, arm64)
pip: 26.2.1

`pip freeze` output:

    numpy==2.5.3
    pandas==2.2.3
    psycopg==3.2.3
    psycopg-binary==3.2.3
    pyarrow==17.0.0
    python-dateutil==2.9.0.post0
    python-dotenv==1.0.1
    pytz==2026.3.post1
    PyYAML==6.0.2
    six==1.17.0
    typing_extensions==4.16.0
    tzdata==2026.4

All five pinned packages resolved to the exact requested versions. The
remaining seven are transitive dependencies pulled in by pandas and
psycopg.

### Why `.venv` is not committed

The virtual environment is listed in `.gitignore` and deliberately not
tracked, for three reasons:

1. It is platform- and interpreter-specific. This one contains
   `macosx_11_0_arm64` binaries built for CPython 3.12; it would not
   work on Linux, on Intel macOS, or on a different Python version.
2. It is fully reproducible from `requirements.txt`, which is the
   artifact that actually defines the environment. Committing both would
   create two sources of truth that can disagree.
3. It is large and changes constantly, which would make the repository
   history unreadable.

Reproducing this environment requires only the pinned interpreter
version recorded above plus `pip install -r requirements.txt`.