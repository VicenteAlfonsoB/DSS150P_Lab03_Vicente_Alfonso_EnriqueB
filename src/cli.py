import argparse

from src.config import PROJECT_ROOT, DB, SETTINGS, path_for
from src.common.audit import new_run_id
from src.extract.files import extract_sources
from src.transform.staging import build_staging
from src.transform.curated import build_curated


def main():
    parser = argparse.ArgumentParser(description='DSS150P modular pipeline')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate-env')
    sub.add_parser('extract')
    sub.add_parser('transform')
    sub.add_parser('load')
    sub.add_parser('validate')
    b = sub.add_parser('benchmark'); b.add_argument('--repeats', type=int, default=5)
    p = sub.add_parser('load-partition'); p.add_argument('--year', type=int, required=True); p.add_argument('--month', type=int, required=True)
    sub.add_parser('run-all')
    args = parser.parse_args()

    if args.command == 'validate-env':
        print('PROJECT_ROOT=', PROJECT_ROOT)
        print('DB host/database=', DB['host'], DB['dbname'])
        print('Configured source=', SETTINGS['pipeline']['source_dir'])
        return

    if args.command == 'extract':
        run_id = new_run_id()
        raw_dir = extract_sources(run_id)
        print(f'run_id={run_id}')
        print(f'raw_dir={raw_dir}')
        return

    if args.command == 'transform':
        run_id = new_run_id()
        raw_dir = path_for('raw_dir') / f'run_id={run_id}'
        if not raw_dir.exists():
            raise FileNotFoundError(
                f'No raw snapshot for run_id={run_id}. Run extract first with '
                f'the same PIPELINE_RUN_ID.')
        staging, q_staging = build_staging(raw_dir, run_id)
        curated, q_curated = build_curated(staging, run_id)
        print(f'run_id={run_id}')
        for name, frame in staging.items():
            print(f'staging.{name} rows={len(frame)}')
        print(f'curated.sales_order_lines rows={len(curated)}')
        print(f'quarantine.total rows={len(q_staging) + len(q_curated)}')
        for frame in (q_staging, q_curated):
            if len(frame):
                print(frame['reason'].value_counts().to_string())
        return

    # TODO: Wire the modular functions together. Keep orchestration logic thin.
    raise NotImplementedError(f'Wire command: {args.command}')

if __name__ == '__main__':
    main()