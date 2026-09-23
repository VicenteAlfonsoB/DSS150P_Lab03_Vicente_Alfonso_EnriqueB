"""DSS150P sales pipeline DAG.

The DAG orchestrates only. Every task shells out to the same CLI used by
hand, so no transformation logic lives here.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator

PROJECT = '/opt/airflow/project'

# Airflow run ids contain ':' and '+', and this value becomes a directory
RUN_ID = '{{ dag_run.run_id | replace(":", "-") | replace("+", "_") }}'

LOAD_COMMAND = (
    '{% if params.run_mode == "partition" %}'
    'load-partition --year {{ params.year }} --month {{ params.month }}'
    '{% else %}'
    'load'
    '{% endif %}'
)


def cli(command: str) -> str:
    return f'cd {PROJECT} && PIPELINE_RUN_ID="{RUN_ID}" python -m src.cli {command}'


def failure_callback(context):
    ti = context['task_instance']
    record = {
        'dag_id': ti.dag_id,
        'task_id': ti.task_id,
        'run_id': context.get('run_id'),
        'try_number': ti.try_number,
        'max_tries': ti.max_tries,
        'state': str(ti.state),
        'logical_date': str(context.get('logical_date')),
        'params': dict(context.get('params') or {}),
        'exception': str(context.get('exception')),
        'log_url': getattr(ti, 'log_url', None),
    }
    print('TASK FAILED:', json.dumps(record, default=str))
    out = Path(PROJECT) / 'logs' / 'dag_failures.jsonl'
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, default=str) + '\n')


DEFAULT_ARGS = {
    'owner': 'dss150p',
    'retries': 2,
    'retry_delay': timedelta(minutes=1),
    'execution_timeout': timedelta(minutes=15),  # a full run takes under a minute
    'on_failure_callback': failure_callback,
}

with DAG(
    dag_id='dss150p_sales_pipeline',
    start_date=datetime(2026, 1, 1),
    schedule='0 2 * * *',
    catchup=False,           # explicit: no backfill of missed intervals
    max_active_runs=1,       # one writer to curated.sales_order_lines at a time
    default_args=DEFAULT_ARGS,
    params={
        'run_mode': Param('full', enum=['full', 'partition']),
        'year': Param(2026, type='integer'),
        'month': Param(1, type='integer', minimum=1, maximum=12),
    },
    tags=['DSS150P'],
) as dag:
    extract = BashOperator(task_id='extract', bash_command=cli('extract'))
    transform = BashOperator(task_id='transform', bash_command=cli('transform'))
    load = BashOperator(task_id='load', bash_command=cli(LOAD_COMMAND))
    validate = BashOperator(task_id='validate', bash_command=cli('validate'))

    extract >> transform >> load >> validate