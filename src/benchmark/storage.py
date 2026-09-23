"""Storage format comparison and partitioned Parquet output."""
import shutil
import statistics
import time
from pathlib import Path

import pandas as pd

from src.config import SETTINGS

BENCH = SETTINGS['storage_benchmark']
FILTER_STATUS = BENCH['filter_status']
PARTITION_COLUMNS = BENCH['partition_columns']
JSON_LINES = BENCH['json_lines']

BENCHMARK_COLUMNS = [
    'storage_type', 'file_size_bytes', 'write_seconds', 'full_read_seconds',
    'filtered_read_seconds', 'row_count', 'notes',
]

BENCH_TABLE = 'curated.benchmark_sales'
MONEY_COLUMNS = ['unit_price', 'discount_pct', 'gross_amount',
                 'discount_amount', 'net_amount']


def _median_time(fn, repeats):
    times, result = [], None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - start)
    return statistics.median(times), result


def _bench_csv(df, out_dir, repeats):
    path = out_dir / 'sales_order_lines.csv'
    write_s, _ = _median_time(lambda: df.to_csv(path, index=False), repeats)
    full_s, full = _median_time(lambda: pd.read_csv(path), repeats)

    def filtered():
        frame = pd.read_csv(path)
        return frame[frame['status'] == FILTER_STATUS]

    filt_s, filt = _median_time(filtered, repeats)
    return {
        'storage_type': 'csv',
        'file_size_bytes': path.stat().st_size,
        'write_seconds': write_s,
        'full_read_seconds': full_s,
        'filtered_read_seconds': filt_s,
        'row_count': len(full),
        'notes': f'row-oriented text, no pushdown; whole file read then filtered; '
                 f'{len(filt)} rows match status={FILTER_STATUS}; types lost on read',
    }


def _bench_jsonl(df, out_dir, repeats):
    path = out_dir / 'sales_order_lines.jsonl'
    encoded = df.copy()
    for c in MONEY_COLUMNS:  # JSON has no decimal type
        encoded[c] = encoded[c].astype(float)

    write_s, _ = _median_time(
        lambda: encoded.to_json(path, orient='records', lines=JSON_LINES,
                                date_format='iso'), repeats)
    full_s, full = _median_time(
        lambda: pd.read_json(path, lines=JSON_LINES), repeats)

    def filtered():
        frame = pd.read_json(path, lines=JSON_LINES)
        return frame[frame['status'] == FILTER_STATUS]

    filt_s, filt = _median_time(filtered, repeats)
    return {
        'storage_type': 'jsonl',
        'file_size_bytes': path.stat().st_size,
        'write_seconds': write_s,
        'full_read_seconds': full_s,
        'filtered_read_seconds': filt_s,
        'row_count': len(full),
        'notes': f'column names repeated on every row; no pushdown; '
                 f'{len(filt)} rows match status={FILTER_STATUS}; '
                 f'NUMERIC converted to float, exact decimal fidelity lost',
    }


def _bench_parquet(df, out_dir, repeats):
    path = out_dir / 'sales_order_lines.parquet'
    write_s, _ = _median_time(lambda: df.to_parquet(path, index=False), repeats)
    full_s, full = _median_time(lambda: pd.read_parquet(path), repeats)
    filt_s, filt = _median_time(
        lambda: pd.read_parquet(path, filters=[('status', '==', FILTER_STATUS)]),
        repeats)
    return {
        'storage_type': 'parquet',
        'file_size_bytes': path.stat().st_size,
        'write_seconds': write_s,
        'full_read_seconds': full_s,
        'filtered_read_seconds': filt_s,
        'row_count': len(full),
        'notes': f'columnar and compressed; predicate pushed down to the reader; '
                 f'{len(filt)} rows match status={FILTER_STATUS}; '
                 f'decimal128 preserves NUMERIC exactly',
    }


def _bench_postgres(df, repeats):
    from src.load.postgres import _connect, _rows, COLUMNS

    def write():
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS {BENCH_TABLE}')
                cur.execute(f'CREATE TABLE {BENCH_TABLE} '
                            f'(LIKE curated.sales_order_lines INCLUDING DEFAULTS)')
                with cur.copy(f"COPY {BENCH_TABLE} ({', '.join(COLUMNS)}) "
                              f"FROM STDIN") as cp:
                    for row in _rows(df):
                        cp.write_row(row)
            conn.commit()

    write_s, _ = _median_time(write, repeats)

    def query(sql, params=None):
        def run():
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall()
        return run

    full_s, full = _median_time(query(f'SELECT * FROM {BENCH_TABLE}'), repeats)
    filt_s, filt = _median_time(
        query(f'SELECT * FROM {BENCH_TABLE} WHERE status = %s', (FILTER_STATUS,)),
        repeats)

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_total_relation_size(%s)', (BENCH_TABLE,))
            size = cur.fetchone()[0]

    return {
        'storage_type': 'postgresql',
        'file_size_bytes': size,
        'write_seconds': write_s,
        'full_read_seconds': full_s,
        'filtered_read_seconds': filt_s,
        'row_count': len(full),
        'notes': f'COPY into an unindexed table, LIKE ... INCLUDING DEFAULTS; '
                 f'{len(filt)} rows match status={FILTER_STATUS}; '
                 f'size from pg_total_relation_size; sequential scan, no index',
    }


def run_benchmark(curated_path, output_dir, repeats: int = 5):
    """Compare the same logical dataset across four storage types."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(curated_path)

    results = [
        _bench_csv(df, output_dir, repeats),
        _bench_jsonl(df, output_dir, repeats),
        _bench_parquet(df, output_dir, repeats),
        _bench_postgres(df, repeats),
    ]
    frame = pd.DataFrame(results)[BENCHMARK_COLUMNS]
    frame.to_csv(output_dir / 'benchmark_results.csv', index=False)
    return frame


def write_partitioned_parquet(df, output_dir):
    output_dir = Path(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)  # rerun-safe: stale partitions would survive otherwise
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = pd.to_datetime(df['order_timestamp'], utc=True)
    out = df.assign(order_year=ts.dt.year, order_month=ts.dt.month)
    out.to_parquet(output_dir, partition_cols=PARTITION_COLUMNS, index=False)
    return output_dir