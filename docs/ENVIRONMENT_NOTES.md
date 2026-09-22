# Environment Notes

Machine: MacBook Air Apple Silicon, macOS, zsh
Author: Vicente Alfonso Enrique B.

## Attempt 1 — Python 3.14.2 (FAILED)

The first virtual environment was built on the system interpreter,
Python 3.14.2, which was the only Python available on this machine.

Commands run:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip     # succeeded, pip 26.2.1
    pip install -r requirements.txt          # FAILED

`pip` reported no matching wheels for the pinned versions and fell back
to downloading source distributions (`.tar.gz`) for both `pandas` and
`pyarrow`. The build then failed:

    error: subprocess-exited-with-error
    x Getting requirements to build wheel did not run successfully.
      exit code: 1
      File "<string>", line 34, in <module>
          ModuleNotFoundError: No module named 'pkg_resources'
    ERROR: Failed to build 'pyarrow' when getting requirements to build wheel

### Diagnosis

This is an interpreter mismatch, not a broken pin. Four of the five
pinned packages were released before Python 3.14 existed, so PyPI
publishes no `cp314` wheel for them:

| Package              | cp314 wheel | Notes                               |
|----------------------|-------------|-------------------------------------|
| pandas==2.2.3        | no          | falls back to source build          |
| pyarrow==17.0.0      | no          | source build requires Arrow C++     |
| psycopg[binary]==3.2.3 | no        | binary distribution, no cp314       |
| python-dotenv==1.0.1 | n/a         | pure Python, installs anywhere      |
| PyYAML==6.0.2        | no          | source build requires Cython        |

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
