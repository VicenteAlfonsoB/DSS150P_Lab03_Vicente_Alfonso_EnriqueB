"""PostgreSQL load with rerun-safe UPSERT semantics."""
from decimal import Decimal

import pandas as pd
import psycopg

from src.config import DB

COLUMNS = [
    'order_id', 'customer_id', 'product_id', 'order_timestamp',
    'customer_city', 'customer_tier', 'product_name', 'category', 'brand',
    'quantity', 'unit_price', 'discount_pct',
    'gross_amount', 'discount_amount', 'net_amount', 'status',
    'source_updated_at', 'pipeline_run_id', 'processed_at_utc', 'record_hash',
]

UPDATE_COLUMNS = [c for c in COLUMNS if c != 'order_id']

INSERT_SQL = f"""
INSERT INTO curated.sales_order_lines ({', '.join(COLUMNS)})
VALUES ({', '.join(['%s'] * len(COLUMNS))})
ON CONFLICT (order_id) DO UPDATE SET
    {', '.join(f'{c} = EXCLUDED.{c}' for c in UPDATE_COLUMNS)}
WHERE curated.sales_order_lines.record_hash IS DISTINCT FROM EXCLUDED.record_hash
"""


def _connect():
    return psycopg.connect(
        host=DB['host'], port=DB['port'], dbname=DB['dbname'],
        user=DB['user'], password=DB['password'],
    )


def _text(value):
    return None if pd.isna(value) else str(value)


def _rows(df):
    for r in df.itertuples(index=False):
        yield (
            str(r.order_id), str(r.customer_id), str(r.product_id),
            pd.Timestamp(r.order_timestamp).to_pydatetime(),
            _text(r.customer_city), _text(r.customer_tier),
            _text(r.product_name), _text(r.category), _text(r.brand),
            int(r.quantity),                      # numpy int64 does not adapt
            Decimal(str(r.unit_price)), Decimal(str(r.discount_pct)),
            Decimal(str(r.gross_amount)), Decimal(str(r.discount_amount)),
            Decimal(str(r.net_amount)),
            str(r.status),
            pd.Timestamp(r.source_updated_at).to_pydatetime(),
            str(r.pipeline_run_id), str(r.processed_at_utc), str(r.record_hash),
        )


def upsert_curated(df, run_id: str) -> int:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, list(_rows(df)))
            affected = cur.rowcount
        conn.commit()
    return affected


def load_partition(df, year: int, month: int, run_id: str) -> int:
    raise NotImplementedError('Implement Goal 3 selected-partition load')