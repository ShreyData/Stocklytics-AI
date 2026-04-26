"""
Data Pipeline Module – Mart Transform Runner.

Refreshes the five BigQuery mart tables from the raw tables:

    stocklytics_mart.sales_daily
    stocklytics_mart.product_sales_daily
    stocklytics_mart.customer_summary
    stocklytics_mart.inventory_health
    stocklytics_mart.dashboard_summary

Table schemas and field names match database_design.md §4 exactly.

Each mart uses MERGE … WHEN MATCHED / WHEN NOT MATCHED so the transform is
idempotent and safe to re-run for the same checkpoint window.

`analytics_last_updated_at` is stamped into every mart row at transform time
and also written to analytics_metadata via repository.update_analytics_metadata.
This field must NOT be updated on a failed transform (see shared_business_rules.md §10).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.cloud import bigquery  # type: ignore

from app.common.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


def _run_query(bq: bigquery.Client, sql: str) -> None:
    """Execute a BigQuery DML statement and wait for completion."""
    job = bq.query(sql)
    job.result()  # blocks until the job finishes; raises on error


# ---------------------------------------------------------------------------
# Individual mart refreshes
# ---------------------------------------------------------------------------

def refresh_sales_daily(
    bq: bigquery.Client,
    *,
    store_id: str,
    analytics_last_updated_at: str,
) -> None:
    """
    Refresh stocklytics_mart.sales_daily for the given store.

    Aggregates transactions_raw by sale_date.
    Existing rows for the same (store_id, sales_date) are replaced.
    """
    project = _settings.bigquery_project_id
    raw = _settings.bigquery_dataset_raw
    mart = _settings.bigquery_dataset_mart

    sql = f"""
    MERGE `{project}.{mart}.sales_daily` AS T
    USING (
        SELECT
            store_id,
            DATE(sale_timestamp) AS sales_date,
            SUM(total_amount)    AS total_sales,
            COUNT(*)             AS transaction_count,
            AVG(total_amount)    AS average_basket_value,
            TIMESTAMP '{analytics_last_updated_at}' AS analytics_last_updated_at
        FROM `{project}.{raw}.transactions_raw`
        WHERE store_id = '{store_id}'
        GROUP BY store_id, DATE(sale_timestamp)
    ) AS S
    ON T.store_id = S.store_id AND T.sales_date = S.sales_date
    WHEN MATCHED THEN
        UPDATE SET
            total_sales                 = S.total_sales,
            transaction_count           = S.transaction_count,
            average_basket_value        = S.average_basket_value,
            analytics_last_updated_at   = S.analytics_last_updated_at
    WHEN NOT MATCHED THEN
        INSERT (store_id, sales_date, total_sales, transaction_count, average_basket_value, analytics_last_updated_at)
        VALUES (S.store_id, S.sales_date, S.total_sales, S.transaction_count, S.average_basket_value, S.analytics_last_updated_at)
    """
    _run_query(bq, sql)
    logger.info("Refreshed sales_daily", extra={"store_id": store_id})


def refresh_product_sales_daily(
    bq: bigquery.Client,
    *,
    store_id: str,
    analytics_last_updated_at: str,
) -> None:
    """
    Refresh stocklytics_mart.product_sales_daily for the given store.

    Joins transaction_items_raw with transactions_raw for the sale date.
    """
    project = _settings.bigquery_project_id
    raw = _settings.bigquery_dataset_raw
    mart = _settings.bigquery_dataset_mart

    sql = f"""
    MERGE `{project}.{mart}.product_sales_daily` AS T
    USING (
        SELECT
            i.store_id,
            DATE(i.sale_timestamp) AS sales_date,
            i.product_id,
            i.product_name,
            SUM(i.quantity)        AS quantity_sold,
            SUM(i.line_total)      AS revenue,
            TIMESTAMP '{analytics_last_updated_at}' AS analytics_last_updated_at
        FROM `{project}.{raw}.transaction_items_raw` AS i
        WHERE i.store_id = '{store_id}'
        GROUP BY i.store_id, DATE(i.sale_timestamp), i.product_id, i.product_name
    ) AS S
    ON T.store_id = S.store_id AND T.sales_date = S.sales_date AND T.product_id = S.product_id
    WHEN MATCHED THEN
        UPDATE SET
            product_name                = S.product_name,
            quantity_sold               = S.quantity_sold,
            revenue                     = S.revenue,
            analytics_last_updated_at   = S.analytics_last_updated_at
    WHEN NOT MATCHED THEN
        INSERT (store_id, sales_date, product_id, product_name, quantity_sold, revenue, analytics_last_updated_at)
        VALUES (S.store_id, S.sales_date, S.product_id, S.product_name, S.quantity_sold, S.revenue, S.analytics_last_updated_at)
    """
    _run_query(bq, sql)
    logger.info("Refreshed product_sales_daily", extra={"store_id": store_id})


def refresh_customer_summary(
    bq: bigquery.Client,
    *,
    store_id: str,
    analytics_last_updated_at: str,
) -> None:
    """Refresh stocklytics_mart.customer_summary for the given store."""
    project = _settings.bigquery_project_id
    raw = _settings.bigquery_dataset_raw
    mart = _settings.bigquery_dataset_mart

    sql = f"""
    MERGE `{project}.{mart}.customer_summary` AS T
    USING (
        SELECT
            store_id,
            customer_id,
            name AS customer_name,
            total_spend AS lifetime_spend,
            visit_count,
            last_purchase_at,
            TIMESTAMP '{analytics_last_updated_at}' AS analytics_last_updated_at
        FROM `{project}.{raw}.customers_raw`
        WHERE store_id = '{store_id}'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY captured_at DESC) = 1
    ) AS S
    ON T.store_id = S.store_id AND T.customer_id = S.customer_id
    WHEN MATCHED THEN
        UPDATE SET
            customer_name               = S.customer_name,
            lifetime_spend              = S.lifetime_spend,
            visit_count                 = S.visit_count,
            last_purchase_at            = S.last_purchase_at,
            analytics_last_updated_at   = S.analytics_last_updated_at
    WHEN NOT MATCHED THEN
        INSERT (store_id, customer_id, customer_name, lifetime_spend, visit_count, last_purchase_at, analytics_last_updated_at)
        VALUES (S.store_id, S.customer_id, S.customer_name, S.lifetime_spend, S.visit_count, S.last_purchase_at, S.analytics_last_updated_at)
    """
    _run_query(bq, sql)
    logger.info("Refreshed customer_summary", extra={"store_id": store_id})


def refresh_inventory_health(
    bq: bigquery.Client,
    *,
    store_id: str,
    analytics_last_updated_at: str,
) -> None:
    """
    Refresh stocklytics_mart.inventory_health.

    Uses the latest inventory snapshot per product.
    Computes days_to_expiry and is_low_stock flags.
    """
    project = _settings.bigquery_project_id
    raw = _settings.bigquery_dataset_raw
    mart = _settings.bigquery_dataset_mart

    sql = f"""
    MERGE `{project}.{mart}.inventory_health` AS T
    USING (
        SELECT
            store_id,
            CURRENT_DATE()                             AS snapshot_date,
            product_id,
            product_name,
            quantity_on_hand,
            reorder_threshold,
            DATE_DIFF(DATE(expiry_date), CURRENT_DATE(), DAY) AS days_to_expiry,
            quantity_on_hand < reorder_threshold       AS is_low_stock,
            TIMESTAMP '{analytics_last_updated_at}'    AS analytics_last_updated_at
        FROM `{project}.{raw}.inventory_snapshot_raw`
        WHERE store_id = '{store_id}'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY captured_at DESC) = 1
    ) AS S
    ON T.store_id = S.store_id AND T.product_id = S.product_id AND T.snapshot_date = S.snapshot_date
    WHEN MATCHED THEN
        UPDATE SET
            product_name                = S.product_name,
            quantity_on_hand            = S.quantity_on_hand,
            reorder_threshold           = S.reorder_threshold,
            days_to_expiry              = S.days_to_expiry,
            is_low_stock                = S.is_low_stock,
            analytics_last_updated_at   = S.analytics_last_updated_at
    WHEN NOT MATCHED THEN
        INSERT (store_id, snapshot_date, product_id, product_name, quantity_on_hand, reorder_threshold, days_to_expiry, is_low_stock, analytics_last_updated_at)
        VALUES (S.store_id, S.snapshot_date, S.product_id, S.product_name, S.quantity_on_hand, S.reorder_threshold, S.days_to_expiry, S.is_low_stock, S.analytics_last_updated_at)
    """
    _run_query(bq, sql)
    logger.info("Refreshed inventory_health", extra={"store_id": store_id})


def refresh_dashboard_summary(
    bq: bigquery.Client,
    *,
    store_id: str,
    analytics_last_updated_at: str,
) -> None:
    """
    Refresh stocklytics_mart.dashboard_summary.

    Derives today's top-level KPIs from the other mart tables.
    """
    project = _settings.bigquery_project_id
    mart = _settings.bigquery_dataset_mart

    sql = f"""
    MERGE `{project}.{mart}.dashboard_summary` AS T
    USING (
        SELECT
            sd.store_id,
            sd.sales_date                                              AS snapshot_date,
            sd.total_sales                                             AS today_sales,
            sd.transaction_count                                       AS today_transactions,
            IFNULL(ac.active_alert_count, 0)                          AS active_alert_count,
            IFNULL(ls.low_stock_count, 0)                             AS low_stock_count,
            tp.product_name                                            AS top_selling_product,
            TIMESTAMP '{analytics_last_updated_at}'                   AS analytics_last_updated_at
        FROM (
            SELECT * FROM `{project}.{mart}.sales_daily`
            WHERE store_id = '{store_id}' AND sales_date = CURRENT_DATE()
        ) AS sd
        LEFT JOIN (
            SELECT store_id, COUNT(*) AS active_alert_count
            FROM `{project}.{mart}.inventory_health`
            WHERE store_id = '{store_id}' AND is_low_stock = TRUE AND snapshot_date = CURRENT_DATE()
            GROUP BY store_id
        ) AS ac ON ac.store_id = sd.store_id
        LEFT JOIN (
            SELECT store_id, COUNT(*) AS low_stock_count
            FROM `{project}.{mart}.inventory_health`
            WHERE store_id = '{store_id}' AND is_low_stock = TRUE AND snapshot_date = CURRENT_DATE()
            GROUP BY store_id
        ) AS ls ON ls.store_id = sd.store_id
        LEFT JOIN (
            SELECT product_name
            FROM `{project}.{mart}.product_sales_daily`
            WHERE store_id = '{store_id}' AND sales_date = CURRENT_DATE()
            ORDER BY quantity_sold DESC LIMIT 1
        ) AS tp ON TRUE
    ) AS S
    ON T.store_id = S.store_id AND T.snapshot_date = S.snapshot_date
    WHEN MATCHED THEN
        UPDATE SET
            today_sales                 = S.today_sales,
            today_transactions          = S.today_transactions,
            active_alert_count          = S.active_alert_count,
            low_stock_count             = S.low_stock_count,
            top_selling_product         = S.top_selling_product,
            analytics_last_updated_at   = S.analytics_last_updated_at
    WHEN NOT MATCHED THEN
        INSERT (store_id, snapshot_date, today_sales, today_transactions, active_alert_count, low_stock_count, top_selling_product, analytics_last_updated_at)
        VALUES (S.store_id, S.snapshot_date, S.today_sales, S.today_transactions, S.active_alert_count, S.low_stock_count, S.top_selling_product, S.analytics_last_updated_at)
    """
    _run_query(bq, sql)
    logger.info("Refreshed dashboard_summary", extra={"store_id": store_id})


# ---------------------------------------------------------------------------
# Public: run all mart transforms in dependency order
# ---------------------------------------------------------------------------

def run_all_mart_transforms(
    bq: bigquery.Client,
    *,
    store_id: str,
    analytics_last_updated_at: datetime,
) -> None:
    """
    Execute all five mart refreshes in dependency order.

    sales_daily and product_sales_daily must come before dashboard_summary
    because dashboard_summary joins against them.

    Raises if any transform fails. The caller (transform_runner) handles retries.
    analytics_last_updated_at is passed through so all mart rows carry the
    same freshness timestamp.
    """
    ts_str = analytics_last_updated_at.isoformat()

    # 1. Foundation marts (independent of each other)
    refresh_sales_daily(bq, store_id=store_id, analytics_last_updated_at=ts_str)
    refresh_product_sales_daily(bq, store_id=store_id, analytics_last_updated_at=ts_str)
    refresh_customer_summary(bq, store_id=store_id, analytics_last_updated_at=ts_str)
    refresh_inventory_health(bq, store_id=store_id, analytics_last_updated_at=ts_str)

    # 2. Summary mart (depends on all above)
    refresh_dashboard_summary(bq, store_id=store_id, analytics_last_updated_at=ts_str)

    logger.info("All mart transforms complete", extra={"store_id": store_id})
