"""Curated layer: analysis-ready sales order lines."""
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from src.config import path_for
from src.common.audit import utc_now_iso, record_hash
from src.transform.staging import _quarantine, _empty_quarantine

CURATED_COLUMNS = [
    'order_id', 'customer_id', 'product_id', 'order_timestamp',
    'customer_city', 'customer_tier', 'product_name', 'category', 'brand',
    'quantity', 'unit_price', 'discount_pct',
    'gross_amount', 'discount_amount', 'net_amount', 'status',
    'source_updated_at', 'pipeline_run_id', 'processed_at_utc', 'record_hash',
]

HASH_KEYS = [  # business content only, never run metadata
    'order_id', 'customer_id', 'product_id', 'order_timestamp',
    'quantity', 'unit_price', 'discount_pct', 'status', 'source_updated_at',
]

TWO_DP = Decimal('0.01')


def build_curated(staging: dict, run_id: str):
    """Join staging datasets into curated sales rows; return (df, quarantine)."""
    orders = staging['orders'].copy()
    customers = staging['customers']
    products = staging['products']

    known_customers = set(customers['customer_id'])
    known_products = set(products['product_id'])

    rejects = []

    bad = ~orders['customer_id'].isin(known_customers)
    rejects.append(_quarantine(orders[bad], 'orders', 'order_id',
                               'orphan_customer_reference', run_id,
                               'customer_id not present in staging customers'))
    orders = orders[~bad].copy()

    bad = ~orders['product_id'].isin(known_products)
    rejects.append(_quarantine(orders[bad], 'orders', 'order_id',
                               'orphan_product_reference', run_id,
                               'product_id missing from source or quarantined upstream'))
    orders = orders[~bad].copy()

    df = orders.merge(
        customers[['customer_id', 'city', 'customer_tier']],
        on='customer_id', how='left',
    ).merge(
        products[['product_id', 'product_name', 'category', 'brand']],
        on='product_id', how='left',
    )
    df = df.rename(columns={'city': 'customer_city', 'updated_at': 'source_updated_at'})

    gross, discount, net = [], [], []
    for q, p, d in zip(df['quantity'], df['unit_price'], df['discount_pct']):
        g = (Decimal(int(q)) * Decimal(str(p))).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        dis = (g * Decimal(str(d))).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        gross.append(g)
        discount.append(dis)
        net.append(g - dis)
    df['gross_amount'] = gross
    df['discount_amount'] = discount
    df['net_amount'] = net

    df['pipeline_run_id'] = run_id
    df['processed_at_utc'] = utc_now_iso()
    df['record_hash'] = [record_hash(r, HASH_KEYS) for r in df.to_dict('records')]
    df = df[CURATED_COLUMNS].sort_values('order_id').reset_index(drop=True)

    populated = [f for f in rejects if not f.empty]
    quarantine = pd.concat(populated, ignore_index=True) if populated else _empty_quarantine()

    curated_dir = path_for('curated_dir') / f'run_id={run_id}'
    curated_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(curated_dir / 'sales_order_lines.parquet', index=False)

    quarantine_file = path_for('quarantine_dir') / f'run_id={run_id}' / 'quarantine.csv'
    if len(quarantine):
        quarantine_file.parent.mkdir(parents=True, exist_ok=True)
        if quarantine_file.exists():  # append to staging's rows, one file per run
            existing = pd.read_csv(quarantine_file)
            combined = pd.concat([existing, quarantine], ignore_index=True)
        else:
            combined = quarantine
        combined.to_csv(quarantine_file, index=False)

    return df, quarantine