## Week 4
- Python version: 3.12.14 (Homebrew, arm64), pip 26.2.1. The first
  attempt used the system interpreter 3.14.2 and failed — no cp314
  wheels exist for the pinned packages and pyarrow could not build from
  source. The interpreter was changed rather than the pins, so that the
  library versions producing the Goal 3 benchmarks stay as specified.
  Full record in docs/ENVIRONMENT_NOTES.md. Evidence:
  python314-pip-install-failure.png, brew-install-python312.png,
  successful-cp312-install.png

- Git status/log evidence: branch `goal1-reproducible-environment`,
  branched from `main`. Commits cover the added .gitignore, the
  .env.example missing from the starter package, the Python 3.14 failure
  record, a correction to that record, the 3.12.14 rebuild, the Docker
  container name collision, and evidence capture. Evidence:
  goal1-git-log.png

- Docker image/container evidence: image
  `dss150p-lab03-starter-main-pipeline` built from `python:3.11-slim`.
  Container `dss150p-postgres` (postgres:16) reports `Up (healthy)` on
  5432. First `docker compose up` failed on a container name collision
  with an exited container from Laboratory Activity 1 — container names
  are global to the Docker daemon, not scoped per compose project.
  Resolved by removing that container only; the Lab 1 volume was
  verified intact with `docker volume ls` before and after. Schemas and
  curated tables verified inside the container with `\dn` and
  `\dt curated.*`. Evidence: docker-build-pipeline-image.png,
  docker-container-conflict-and-fix.png,
  postgres-schema-verification.png

- External configuration evidence: `python -m src.cli validate-env`
  prints `DB host/database= localhost dss150p` on the host and
  `DB host/database= postgres dss150p` inside the container. The value
  changes because docker-compose.yml overrides POSTGRES_HOST for the
  pipeline service; no code, settings.yml entry, or SQL file changed
  between the two runs. Evidence: validate-env.png,
  docker-container-conflict-and-fix.png

  Section 7.3 scan `git grep -n "change_me" -- ":(exclude).env.example"`
  returns three matches, all in starter-provided files:
  `docker-compose.yml:7`, `docker-compose.airflow.yml:12`, and
  `src/config.py:17`. All three are fallback defaults
  (`${POSTGRES_PASSWORD:-change_me}` and
  `os.getenv('POSTGRES_PASSWORD', 'change_me')`), not stored
  credentials — the literal `change_me` serves the same placeholder role
  it serves in `.env.example`. The working password exists only in
  `.env`, which is untracked: `git check-ignore -v .env` names
  `.gitignore:4` as the excluding rule, `git ls-files` shows
  `.env.example` as the only tracked `.env*` file, and
  `git log --all --oneline -- .env` returns no commits, confirming it
  was never committed at any point in the history. These defaults were
  left unmodified because they are instructor-provided scaffolding.
  Evidence: secret-scan-verification.png