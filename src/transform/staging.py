"""Staging layer: cleaned, typed, deduplicated datasets plus quarantine."""
import json
from pathlib import Path

import pandas as pd

from src.config import path_for, SETTINGS
from src.common.audit import utc_now_iso

Q = SETTINGS['quality']
ALLOWED_STATUSES = set(Q['allowed_order_statuses'])
MIN_QTY = int(Q['min_quantity'])
MAX_QTY = int(Q['max_quantity'])

QUARANTINE_COLUMNS = [
    'dataset', 'business_key', 'reason', 'detail',
    'pipeline_run_id', 'quarantined_at_utc', 'record',
]


def _empty_quarantine():
    return pd.DataFrame(columns=QUARANTINE_COLUMNS)


def _quarantine(df, dataset, key_col, reason, run_id, detail=''):
    if df.empty:
        return _empty_quarantine()
    return pd.DataFrame({
        'dataset': dataset,
        'business_key': df[key_col].astype(str).values,
        'reason': reason,
        'detail': detail,
        'pipeline_run_id': run_id,
        'quarantined_at_utc': utc_now_iso(),
        'record': [json.dumps(r, default=str) for r in df.to_dict('records')],
    })


def _dedupe(df, key, updated_col):
    """Keep the greatest updated_at per key; ties break on source file order."""
    ordered = df.reset_index(drop=True).rename_axis('_source_row').reset_index()
    ordered = ordered.sort_values([updated_col, '_source_row'], kind='mergesort')
    kept = ordered.drop_duplicates(subset=[key], keep='last')
    return kept.drop(columns='_source_row').sort_values(key).reset_index(drop=True)


def _stage_customers(raw_dir, run_id):
    df = pd.read_csv(raw_dir / 'customers.csv', dtype=str)
    df['created_at'] = pd.to_datetime(df['created_at'], utc=True, errors='coerce')
    df['updated_at'] = pd.to_datetime(df['updated_at'], utc=True, errors='coerce')
    df['email'] = df['email'].str.strip().str.lower()
    df['city'] = df['city'].str.strip().str.title()
    df['customer_tier'] = df['customer_tier'].str.strip()
    df = _dedupe(df, 'customer_id', 'updated_at')
    df = df.assign(pipeline_run_id=run_id, staged_at_utc=utc_now_iso())
    return df, _empty_quarantine()  # blank email is not a rejection reason


def _stage_products(raw_dir, run_id):
    with (raw_dir / 'products.json').open(encoding='utf-8') as f:
        df = pd.json_normalize(json.load(f))
    df = df.rename(columns={
        'name': 'product_name',
        'category.name': 'category',
        'category.department': 'category_department',
    })
    df['updated_at'] = pd.to_datetime(df['updated_at'], utc=True, errors='coerce')
    df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce')
    for c in ('product_name', 'category', 'brand'):
        df[c] = df[c].astype(str).str.strip()

    df = _dedupe(df, 'product_id', 'updated_at')  # validate the surviving version

    invalid = df['unit_price'].isna() | (df['unit_price'] <= 0)
    quarantine = _quarantine(
        df[invalid], 'products', 'product_id',
        'product_unit_price_not_positive', run_id,
        'unit_price must be greater than 0',
    )
    df = df[~invalid].copy()
    df = df.assign(pipeline_run_id=run_id, staged_at_utc=utc_now_iso())
    return df, quarantine


def _stage_orders(raw_dir, run_id):
    df = pd.read_csv(raw_dir / 'orders.csv', dtype=str)
    df['order_timestamp'] = pd.to_datetime(df['order_timestamp'], utc=True, errors='coerce')
    df['updated_at'] = pd.to_datetime(df['updated_at'], utc=True, errors='coerce')
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
    df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce')
    df['discount_pct'] = pd.to_numeric(df['discount_pct'], errors='coerce')
    df['status'] = df['status'].astype(str).str.strip().str.upper()

    df = _dedupe(df, 'order_id', 'updated_at')

    rejects = []  # rules run in order, first failure wins, one reason per record

    bad = df['order_timestamp'].isna()
    rejects.append(_quarantine(df[bad], 'orders', 'order_id',
                               'order_timestamp_unparseable', run_id,
                               'order_timestamp could not be parsed as UTC'))
    df = df[~bad].copy()

    bad = df['quantity'].isna() | (df['quantity'] < MIN_QTY) | (df['quantity'] > MAX_QTY)
    rejects.append(_quarantine(df[bad], 'orders', 'order_id',
                               'order_quantity_out_of_range', run_id,
                               f'quantity must be between {MIN_QTY} and {MAX_QTY}'))
    df = df[~bad].copy()

    bad = ~df['status'].isin(ALLOWED_STATUSES)
    rejects.append(_quarantine(df[bad], 'orders', 'order_id',
                               'order_status_not_allowed', run_id,
                               f'status must be one of {sorted(ALLOWED_STATUSES)}'))
    df = df[~bad].copy()

    bad = df['unit_price'].isna() | (df['unit_price'] <= 0)
    rejects.append(_quarantine(df[bad], 'orders', 'order_id',
                               'order_unit_price_not_positive', run_id,
                               'unit_price must be greater than 0'))
    df = df[~bad].copy()

    bad = df['discount_pct'].isna() | (df['discount_pct'] < 0) | (df['discount_pct'] > 1)
    rejects.append(_quarantine(df[bad], 'orders', 'order_id',
                               'order_discount_pct_out_of_range', run_id,
                               'discount_pct must be between 0 and 1'))
    df = df[~bad].copy()

    df['quantity'] = df['quantity'].astype(int)
    df = df.assign(pipeline_run_id=run_id, staged_at_utc=utc_now_iso())

    populated = [f for f in rejects if not f.empty]
    quarantine = pd.concat(populated, ignore_index=True) if populated else _empty_quarantine()
    return df, quarantine


def build_staging(raw_dir, run_id: str):
    """Return a dict of staging DataFrames and one combined quarantine DataFrame."""
    raw_dir = Path(raw_dir)

    customers, q_customers = _stage_customers(raw_dir, run_id)
    products, q_products = _stage_products(raw_dir, run_id)
    orders, q_orders = _stage_orders(raw_dir, run_id)

    staging = {'customers': customers, 'products': products, 'orders': orders}

    populated = [f for f in (q_customers, q_products, q_orders) if not f.empty]
    quarantine = pd.concat(populated, ignore_index=True) if populated else _empty_quarantine()

    staging_dir = path_for('staging_dir') / f'run_id={run_id}'
    staging_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in staging.items():
        frame.to_parquet(staging_dir / f'{name}.parquet', index=False)  # keeps types

    quarantine_dir = path_for('quarantine_dir') / f'run_id={run_id}'
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    quarantine.to_csv(quarantine_dir / 'quarantine.csv', index=False)  # read by people

    return staging, quarantine