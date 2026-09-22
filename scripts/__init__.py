"""Exploratory profiling of the three source datasets.

Not part of the pipeline. Reads data/source/ read-only and prints findings.
The dataset guide states that defects exist but deliberately does not say
where, so this script locates them. Staging rules are then written against
observed problems rather than assumed ones.

Run:  python -m scripts.profile_sources
"""
import json

import pandas as pd

from src.config import path_for, SETTINGS

SRC = path_for('source_dir')
Q = SETTINGS['quality']
ALLOWED_STATUSES = Q['allowed_order_statuses']
MIN_QTY = Q['min_quantity']
MAX_QTY = Q['max_quantity']

pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 60)


def banner(text):
    print('\n' + '=' * 72)
    print(text)
    print('=' * 72)


def load_sources():
    customers = pd.read_csv(SRC / 'customers.csv', dtype=str)
    orders = pd.read_csv(SRC / 'orders.csv', dtype=str)
    with (SRC / 'products.json').open(encoding='utf-8') as f:
        products = pd.json_normalize(json.load(f))
    return customers, orders, products


def basic(name, df, key, updated_col):
    banner(f'{name} - shape, columns, nulls')
    print(f'rows = {len(df)}')
    print(f'columns = {list(df.columns)}')
    nulls = df.isna().sum()
    nulls = nulls[nulls > 0]
    print('\nnull counts:')
    print(nulls.to_string() if len(nulls) else '  (none)')

    banner(f'{name} - duplicate business keys on {key}')
    n_keys = df[key].nunique()
    print(f'distinct {key} = {n_keys}   rows = {len(df)}   extra rows = {len(df) - n_keys}')
    dupes = df[df.duplicated(subset=[key], keep=False)].sort_values([key, updated_col])
    if len(dupes):
        print(f'\nrows in duplicate groups = {len(dupes)}')
        cols = [key, updated_col] + [c for c in df.columns if c not in (key, updated_col)][:4]
        print(dupes[cols].head(12).to_string(index=False))
    else:
        print('  (none)')


def timestamps(name, df, cols):
    banner(f'{name} - timestamp parsing (UTC)')
    for c in cols:
        parsed = pd.to_datetime(df[c], utc=True, errors='coerce')
        bad = parsed.isna() & df[c].notna()
        print(f'{c}: unparseable={int(bad.sum())} null={int(df[c].isna().sum())} '
              f'min={parsed.min()} max={parsed.max()}')
        if bad.any():
            print(df.loc[bad, [df.columns[0], c]].head(5).to_string(index=False))


def numerics(name, df, cols):
    banner(f'{name} - numeric coercion and ranges')
    for c in cols:
        num = pd.to_numeric(df[c], errors='coerce')
        bad = num.isna() & df[c].notna()
        print(f'\n{c}: non-numeric={int(bad.sum())} null={int(df[c].isna().sum())}')
        if num.notna().any():
            print(f'  min={num.min()}  max={num.max()}  mean={num.mean():.4f}')
        if bad.any():
            print(df.loc[bad, [df.columns[0], c]].head(5).to_string(index=False))


def main():
    customers, orders, products = load_sources()

    # ---------- customers ----------
    basic('customers.csv', customers, 'customer_id', 'updated_at')
    timestamps('customers.csv', customers, ['created_at', 'updated_at'])

    banner('customers.csv - blank or whitespace-only text fields')
    for c in ['first_name', 'last_name', 'email', 'city', 'customer_tier']:
        blank = customers[c].isna() | (customers[c].astype(str).str.strip() == '')
        print(f'{c}: blank = {int(blank.sum())}')

    banner('customers.csv - value checks')
    print('customer_tier values:')
    print(customers['customer_tier'].value_counts(dropna=False).to_string())
    no_at = customers['email'].notna() & ~customers['email'].astype(str).str.contains('@', regex=False)
    print(f'\nemails without "@" = {int(no_at.sum())}')
    if no_at.any():
        print(customers.loc[no_at, ['customer_id', 'email']].head(10).to_string(index=False))
    city = customers['city'].dropna().astype(str)
    odd = city[(city != city.str.strip()) | (city != city.str.title())]
    print(f'\ncity values needing normalization = {len(odd)}')
    if len(odd):
        print(odd.head(10).to_string())

    # ---------- products ----------
    basic('products.json', products, 'product_id', 'updated_at')
    timestamps('products.json', products, ['updated_at'])
    numerics('products.json', products, ['unit_price'])

    banner('products.json - flattened category and active flag')
    print('columns after json_normalize:', list(products.columns))
    print('\ncategory.name top values:')
    print(products['category.name'].value_counts(dropna=False).head(10).to_string())
    print('\nactive values:')
    print(products['active'].value_counts(dropna=False).to_string())

    # ---------- orders ----------
    basic('orders.csv', orders, 'order_id', 'updated_at')
    timestamps('orders.csv', orders, ['order_timestamp', 'updated_at'])
    numerics('orders.csv', orders, ['quantity', 'unit_price', 'discount_pct'])

    banner('orders.csv - status values vs allowed list')
    print(f'allowed = {ALLOWED_STATUSES}')
    print(orders['status'].value_counts(dropna=False).to_string())
    bad_status = ~orders['status'].isin(ALLOWED_STATUSES)
    print(f'\nrows with disallowed status = {int(bad_status.sum())}')
    if bad_status.any():
        print(orders.loc[bad_status, ['order_id', 'status']].head(10).to_string(index=False))

    banner(f'orders.csv - quantity outside [{MIN_QTY}, {MAX_QTY}]')
    qty = pd.to_numeric(orders['quantity'], errors='coerce')
    out = qty.notna() & ((qty < MIN_QTY) | (qty > MAX_QTY))
    print(f'rows = {int(out.sum())}')
    if out.any():
        print(orders.loc[out, ['order_id', 'quantity']].head(10).to_string(index=False))

    banner('orders.csv - discount_pct out of range, non-positive price')
    disc = pd.to_numeric(orders['discount_pct'], errors='coerce')
    bad_disc = disc.notna() & ((disc < 0) | (disc > 1))
    print(f'discount_pct outside [0, 1] = {int(bad_disc.sum())}')
    if bad_disc.any():
        print(orders.loc[bad_disc, ['order_id', 'discount_pct']].head(10).to_string(index=False))
    price = pd.to_numeric(orders['unit_price'], errors='coerce')
    bad_price = price.notna() & (price <= 0)
    print(f'unit_price <= 0 = {int(bad_price.sum())}')
    if bad_price.any():
        print(orders.loc[bad_price, ['order_id', 'unit_price']].head(10).to_string(index=False))

    banner('orders.csv - orphan references')
    cust_ids = set(customers['customer_id'].dropna())
    prod_ids = set(products['product_id'].dropna())
    orphan_c = ~orders['customer_id'].isin(cust_ids)
    orphan_p = ~orders['product_id'].isin(prod_ids)
    print(f'orders with unknown customer_id = {int(orphan_c.sum())}')
    if orphan_c.any():
        print(orders.loc[orphan_c, ['order_id', 'customer_id']].head(10).to_string(index=False))
    print(f'\norders with unknown product_id = {int(orphan_p.sum())}')
    if orphan_p.any():
        print(orders.loc[orphan_p, ['order_id', 'product_id']].head(10).to_string(index=False))

    banner('summary')
    print(f'customers rows={len(customers)} distinct={customers["customer_id"].nunique()}')
    print(f'products  rows={len(products)} distinct={products["product_id"].nunique()}')
    print(f'orders    rows={len(orders)} distinct={orders["order_id"].nunique()}')


if __name__ == '__main__':
    main()