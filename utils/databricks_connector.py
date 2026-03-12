"""
utils/databricks_connector.py — Databricks Integration Point
Intelli-Credit | Production Integration Stub

In production, this module would:
1. Read historical credit data from Databricks Delta Lake
2. Write extraction_payload, research_payload, and recommendation_payload
   to a Databricks Unity Catalog managed table
3. Enable model training / fine-tuning on historical credit decisions
4. Pull sector benchmarks from Databricks Feature Store
5. Run batch scoring using MLflow-deployed PD/LGD models

For this hackathon demo:
- Data is read/written to ./data/*.json (local files)
- The JSON schema is designed to be compatible with Databricks Delta tables
- All dict keys map to Delta table column names directly

=======================================================================
TO ENABLE DATABRICKS INTEGRATION:
=======================================================================
1. Set environment variables in .env or st.secrets:
     DATABRICKS_ENABLED=true
     DATABRICKS_HOST=https://<your-workspace>.azuredatabricks.net
     DATABRICKS_TOKEN=dapi...
     DATABRICKS_CATALOG=intelli_credit
     DATABRICKS_SCHEMA=credit_pipeline
     DATABRICKS_WAREHOUSE_ID=<sql-warehouse-id>

2. Install: pip install databricks-sdk

3. The schema for each Delta table would be:
   extraction_payloads:
     company_name STRING, cin STRING, sector STRING,
     revenue_cr DOUBLE, ebitda_cr DOUBLE, total_debt_cr DOUBLE,
     net_worth_cr DOUBLE, pd DOUBLE, lgd DOUBLE, decision STRING,
     payload_json STRING, created_at TIMESTAMP

   research_payloads: (similar schema)
   recommendation_payloads: (similar schema)

=======================================================================
PRODUCTION CODE (disabled in demo mode):
=======================================================================

from databricks.sdk import WorkspaceClient
import json, os
from datetime import datetime

def _get_databricks_client():
    return WorkspaceClient(
        host=os.getenv("DATABRICKS_HOST"),
        token=os.getenv("DATABRICKS_TOKEN")
    )

def write_payload_to_databricks_production(
    payload_name: str,
    payload: dict,
    company_name: str
) -> bool:
    w = _get_databricks_client()
    catalog  = os.getenv("DATABRICKS_CATALOG",  "intelli_credit")
    schema   = os.getenv("DATABRICKS_SCHEMA",   "credit_pipeline")
    wh_id    = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
    table    = f"{catalog}.{schema}.{payload_name}s"

    payload_json = json.dumps(payload, default=str)
    stmt = (
        f"INSERT INTO {table} "
        f"(company_name, payload_json, created_at) VALUES "
        f"('{company_name}', '{payload_json}', '{datetime.now().isoformat()}')"
    )
    result = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=stmt,
    )
    return result.status.state.value == "SUCCEEDED"
"""

import json
import os


def write_payload_to_databricks(payload_name: str, payload: dict) -> bool:
    """
    Demo mode: writes payload to local ./data/<name>.json.
    In production, configure DATABRICKS_ENABLED=true and
    this will write to Unity Catalog Delta tables instead.
    """
    _enabled = os.getenv("DATABRICKS_ENABLED", "false").lower() == "true"
    if _enabled:
        # Production path — see module docstring for full implementation
        raise NotImplementedError(
            "Set DATABRICKS_ENABLED=false or install databricks-sdk and "
            "configure DATABRICKS_HOST + DATABRICKS_TOKEN."
        )

    # Demo path — local JSON
    os.makedirs("./data", exist_ok=True)
    filepath = f"./data/{payload_name}.json"
    with open(filepath, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return True


def read_payload_from_databricks(payload_name: str) -> dict | None:
    """
    Demo mode: reads payload from local ./data/<name>.json.
    In production, reads from Delta table with latest record per company.
    """
    filepath = f"./data/{payload_name}.json"
    try:
        with open(filepath) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
