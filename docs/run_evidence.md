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

  ## Week 5
- Raw row counts: customers.csv 3003, products.json 601, orders.csv 50005.
  Copied unchanged into data/raw/run_id=<run_id>/ with copy2.

- Staging row counts: customers 3000, products 599, orders 49998.
  Customers lost 3 duplicate versions (C00120, C01250, C02600 — newer
  versions differ only by email casing). Products lost 1 duplicate (P0300,
  superseded by "Nova Tablet 300 Rev2") and 1 record failing the price
  rule. Orders lost 5 duplicate versions and 2 rule failures.

- Curated row counts: 49897.

- Quarantine row counts: 104, every row carrying dataset, business key,
  rule, detail, and the original record as JSON:
    product_unit_price_not_positive   1
    order_quantity_out_of_range       1   (O0000112, quantity 0)
    order_status_not_allowed          1   (O0004445, status UNKNOWN)
    orphan_customer_reference         1   (O0002223, customer C99999)
    orphan_product_reference        100
  The 100 orphan product references are the cascade from quarantining the
  one negative-price product: those orders reference a product the pipeline
  could not vouch for, so they are rejected with a traceable reason rather
  than published with an unreliable price.

- First load affected rows: 49897.

- Second rerun affected rows / evidence of idempotency: 0. The UPSERT is
  `ON CONFLICT (order_id) DO UPDATE ... WHERE record_hash IS DISTINCT FROM
  EXCLUDED.record_hash`, so an unchanged record is not rewritten and is not
  counted. After both runs, `SELECT count(*), count(DISTINCT order_id)`
  returns 49897 and 49897. A later `run-all` with a different run_id also
  reported 0 affected rows, because record_hash covers business content
  only and excludes pipeline_run_id and processed_at_utc.
  Evidence: docs/evidence/goal2/load-idempotency.png,
  docs/evidence/goal2/curated-distinct-orders.png,
  docs/evidence/goal2/run-all-and-pipeline-runs.png

## Week 6
- Benchmark table attached: yes.
  data/benchmarks/run_id=run_manual_002/benchmark_results.csv, committed
  with -f since data/benchmarks/ is otherwise gitignored. Medians of 5
  repetitions over 49,897 curated rows, measured on this machine
  (MacBook Air, Apple Silicon arm64, macOS):

    storage_type  file_size_bytes  write_s   full_read_s  filtered_read_s
    csv               14,193,582   0.316258     0.114239         0.107082
    jsonl             29,891,684   0.340771     0.238224         0.273112
    parquet            5,433,864   0.129019     0.031575         0.009790
    postgresql        13,639,680   0.386492     0.192824         0.037187

  Filtered read selects status = DELIVERED. Parquet won every axis:
  0.38x CSV size, 0.41x CSV write time, 3.6x faster full read, 10.9x
  faster filtered read. Its filtered read is 3.2x faster than its own
  full read, which is predicate pushdown working. JSONL's filtered read
  is slower than its full read, because filtering a format with no
  pushdown is pure added work. Full reasoning in docs/storage_analysis.md.
  Evidence: docs/evidence/goal3/benchmark-table.png,
  docs/evidence/goal3/file-sizes-and-partitions.png

- Partition selected: order_year=2026 / order_month=1.
  Curated output is written as Hive-partitioned Parquet under
  data/partitioned/run_id=<run_id>/order_year=<yyyy>/order_month=<m>/,
  producing 21 partitions (12 months of 2025, 9 of 2026 — the source
  ends 2026-09-12). `load-partition` reads only the one requested
  directory, so loading January 2026 never opens the other 20.

- Partition row count: 2506, agreed by three independent counts —
  rows_loaded reported by the CLI, row_count in audit.partition_loads,
  and a direct count against curated.sales_order_lines.
  Evidence: docs/evidence/goal3/partition-load.png

- PostgreSQL verification query:

    SELECT * FROM audit.partition_loads;

    partition_key                  | loaded_at_utc                 | row_count | pipeline_run_id
    order_year=2026/order_month=1  | 2026-09-23 09:39:15.445865+00 |      2506 | run_manual_002

    SELECT count(*) FROM curated.sales_order_lines
     WHERE date_part('year',  order_timestamp) = 2026
       AND date_part('month', order_timestamp) = 1;

    count
    -----
     2506

  audit.partition_loads is keyed on partition_key with ON CONFLICT DO
  UPDATE, so reloading a partition refreshes its audit row rather than
  appending a duplicate.
  
  ## Week 7
- DAG ID: dss150p_sales_pipeline

- Schedule: `0 2 * * *` (02:00 UTC daily), start_date 2026-01-01,
  catchup=False set explicitly so missed intervals are not backfilled,
  max_active_runs=1 because every run writes the same curated table and
  concurrent runs would race on the same order_ids. The scheduler fired
  run `scheduled__2026-09-22T02:00:00+00:00` on its own, confirming the
  cron works rather than merely parsing, and catchup=False meant it
  scheduled only the most recent interval instead of every 02:00 since
  January.

- Parameters used: run_mode (enum full|partition), year (integer),
  month (integer 1-12). run_mode is applied in the Jinja template of the
  load task, selecting between `python -m src.cli load` and
  `python -m src.cli load-partition --year {{ params.year }} --month
  {{ params.month }}`. The DAG chooses between existing CLI commands; it
  does not reimplement loading. year and month are read only in partition
  mode — a run with year=2024 and run_mode=full succeeded, because the
  full branch ignores them.

- Successful run ID: manual__2026-09-23T12:08:23+00:00
  All four tasks green in order extract → transform → load → validate.
  Also scheduled__2026-09-22T02:00:00+00:00, fired by the scheduler, whose
  load task reported rows_affected=0 — the record_hash guard holding
  through the orchestrator, not just from the command line.
  Evidence: dag-success-graph.png, load-task-log-scheduled.png

- Deliberate failure run ID: manual__2026-09-23T12:17:50+00:00
  Triggered with run_mode=partition, year=2024, month=1. The dataset spans
  2025-2026 only, so no order_year=2024 partition exists. No code was
  modified to produce this failure; the run asks the pipeline for
  something real that is genuinely absent.
  Evidence: dag-deliberate-failure.png

- Retry/failure-handling evidence:
  * retries=2 with retry_delay=1 minute. The task Details panel shows
    Task Tries 1 and 2 as failed against Max Tries 2, then a third and
    final attempt.
  * load raised FileNotFoundError naming the missing partition path,
    exactly the error raised when the same command is run by hand.
  * on_failure_callback wrote a structured record to the task log and to
    logs/dag_failures.jsonl, carrying dag_id, task_id, run_id, try_number,
    max_tries, state, params, exception, and log_url.
  * validate never ran. Its trigger rule is all_success, so it was held at
    upstream_failed. This matters: without it, validation would have run
    against the previous run's data and reported "all checks passed",
    which is worse than failing.
  * execution_timeout=15 minutes is set on every task. A full run takes
    under a minute, so the timeout detects a hang rather than budgeting
    performance.
  Evidence: retry-attempts.png, failure-log-and-retries.png

- Final recovery run ID: manual__2026-09-23T12:28:20+00:00
  Same run_mode=partition with year=2026, month=1. The load task ran the
  identical command shape and reported
  partition=order_year=2026/order_month=1 and rows_loaded=2506, exit code
  0, with all four tasks green. audit.partition_loads shows the row keyed
  order_year=2026/order_month=1 updated in place with the recovery run's
  pipeline_run_id rather than duplicated, because the insert is guarded by
  ON CONFLICT (partition_key) DO UPDATE.
  Evidence: dag-recovery-run.png, recovery-load-partition-log.png,
  audit-and-failure-record.png