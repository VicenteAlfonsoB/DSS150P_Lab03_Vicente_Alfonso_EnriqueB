"""Data quality validation for the curated layer."""
from src.config import SETTINGS

Q = SETTINGS['quality']
ALLOWED_STATUSES = set(Q['allowed_order_statuses'])
MIN_QTY = int(Q['min_quantity'])
MAX_QTY = int(Q['max_quantity'])

REQUIRED_AUDIT_COLUMNS = [
    'source_updated_at', 'pipeline_run_id', 'processed_at_utc', 'record_hash',
]


def validate_curated(df) -> list[str]:
    """Return human-readable validation errors; empty list means the data passed."""
    errors = []

    missing = [c for c in REQUIRED_AUDIT_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f'missing required audit columns: {missing}')

    nulls = int(df['order_id'].isna().sum())
    if nulls:
        errors.append(f'order_id has {nulls} null values')

    dupes = len(df) - int(df['order_id'].nunique())
    if dupes:
        errors.append(f'order_id is not unique: {dupes} duplicate rows')

    bad_qty = int(((df['quantity'] < MIN_QTY) | (df['quantity'] > MAX_QTY)).sum())
    if bad_qty:
        errors.append(f'{bad_qty} rows have quantity outside [{MIN_QTY}, {MAX_QTY}]')

    for col in ('gross_amount', 'discount_amount', 'net_amount'):
        negative = int((df[col] < 0).sum())
        if negative:
            errors.append(f'{negative} rows have negative {col}')

    bad_status = int((~df['status'].isin(ALLOWED_STATUSES)).sum())
    if bad_status:
        errors.append(f'{bad_status} rows have a status outside {sorted(ALLOWED_STATUSES)}')

    for col in REQUIRED_AUDIT_COLUMNS:
        if col in df.columns:
            n = int(df[col].isna().sum())
            if n:
                errors.append(f'{n} rows have null {col}')

    mismatch = int((df['net_amount'] != df['gross_amount'] - df['discount_amount']).sum())
    if mismatch:
        errors.append(f'{mismatch} rows where net_amount != gross_amount - discount_amount')

    return errors