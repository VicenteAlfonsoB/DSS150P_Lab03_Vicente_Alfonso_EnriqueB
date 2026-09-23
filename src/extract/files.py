from pathlib import Path
import shutil

from src.config import path_for

SOURCE_FILES = ('customers.csv', 'products.json', 'orders.csv')


def extract_sources(run_id: str) -> Path:
    """Copy immutable source snapshots into a run-specific raw directory.

    The raw layer is a byte-for-byte copy of what the source looked like at
    the moment this run started. Nothing is parsed, cleaned, or validated
    here — that is staging's job. Keeping raw untouched is what makes a run
    reproducible after the source files have moved on.
    """
    source_dir = path_for('source_dir')
    raw_dir = path_for('raw_dir') / f'run_id={run_id}'
    raw_dir.mkdir(parents=True, exist_ok=True)

    for name in SOURCE_FILES:
        src = source_dir / name
        if not src.exists():
            raise FileNotFoundError(f'Expected source file not found: {src}')
        shutil.copy2(src, raw_dir / name)

    return raw_dir