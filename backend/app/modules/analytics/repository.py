import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from google.cloud import bigquery, firestore

from app.common.config import get_settings
from app.common.google_clients import (
    create_bigquery_client,
    create_firestore_async_client,
    get_default_gcp_project,
)

logger = logging.getLogger(__name__)


class AnalyticsRepository:
    def __init__(self):
        settings = get_settings()
        self.firestore_project_id = settings.firestore_project_id
        self.bigquery_project_id = get_default_gcp_project(settings)
        self.dataset_mart = settings.bigquery_dataset_mart
        self.dataset_raw = settings.bigquery_dataset_raw
        self.project = self.bigquery_project_id
        self._db: Optional[firestore.AsyncClient] = None
        self._bq: Optional[bigquery.Client] = None

    @property
    def db(self) -> firestore.AsyncClient:
        if self._db is None:
            self._db = create_firestore_async_client(project=self.firestore_project_id or None)
        return self._db

    @property
    def bq(self) -> bigquery.Client:
        if self._bq is None:
            self._bq = create_bigquery_client(project=self.bigquery_project_id or None)
        return self._bq

    async def get_analytics_metadata(self, store_id: str) -> Optional[Dict[str, Any]]:
        doc_ref = self.db.collection("analytics_metadata").document(f"{store_id}_dashboard")
        doc = await doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def _run_query(self, query: str, parameters: List[bigquery.ScalarQueryParameter]) -> List[Dict[str, Any]]:
        job_config = bigquery.QueryJobConfig(query_parameters=parameters)
        query_job = self.bq.query(query, job_config=job_config)
        results = query_job.result()
        return [dict(row) for row in results]

    async def get_dashboard_summary(self, store_id: str) -> Optional[Dict[str, Any]]:
        query = f"""
            WITH latest_dashboard AS (
                SELECT
                    today_sales,
                    today_transactions,
                    active_alert_count,
                    low_stock_count,
                    top_selling_product
                FROM `{self.project}.{self.dataset_mart}.dashboard_summary`
                WHERE store_id = @store_id
                ORDER BY snapshot_date DESC
                LIMIT 1
            ),
            latest_alert_status AS (
                SELECT
                    alert_id,
                    status
                FROM `{self.project}.{self.dataset_raw}.alerts_raw`
                WHERE store_id = @store_id
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY alert_id
                    ORDER BY captured_at DESC
                ) = 1
            ),
            alert_truth AS (
                SELECT
                    COUNTIF(status = 'ACTIVE') AS active_alert_count
                FROM latest_alert_status
            )
            SELECT
                d.today_sales,
                d.today_transactions,
                COALESCE(a.active_alert_count, d.active_alert_count, 0) AS active_alert_count,
                d.low_stock_count,
                d.top_selling_product
            FROM latest_dashboard AS d
            LEFT JOIN alert_truth AS a
            ON TRUE
        """
        params = [bigquery.ScalarQueryParameter("store_id", "STRING", store_id)]
        try:
            rows = await asyncio.to_thread(self._run_query, query, params)
        except Exception as exc:
            logger.warning(
                "Falling back to dashboard_summary-only active_alert_count query.",
                extra={"store_id": store_id, "error": str(exc)},
            )
            fallback_query = f"""
                SELECT today_sales, today_transactions, active_alert_count, low_stock_count, top_selling_product
                FROM `{self.project}.{self.dataset_mart}.dashboard_summary`
                WHERE store_id = @store_id
                ORDER BY snapshot_date DESC
                LIMIT 1
            """
            rows = await asyncio.to_thread(self._run_query, fallback_query, params)
        if rows:
            row = rows[0]
            # Convert decimal/float accurately if needed, simple float wrapping
            return {
                "today_sales": float(row.get("today_sales", 0.0)),
                "today_transactions": int(row.get("today_transactions", 0)),
                "active_alert_count": int(row.get("active_alert_count", 0)),
                "low_stock_count": int(row.get("low_stock_count", 0)),
                "top_selling_product": row.get("top_selling_product"),
            }
        return None

    async def get_live_dashboard_summary(self, store_id: str) -> Dict[str, Any]:
        """
        Build an operational dashboard summary directly from Firestore.

        This powers UI cards that should update immediately after inventory and
        billing writes, without waiting for the analytics pipeline.
        """
        now_utc = datetime.now(timezone.utc)
        start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        transactions_query = self.db.collection("transactions").where("store_id", "==", store_id)
        products_query = self.db.collection("products").where("store_id", "==", store_id)
        alerts_query = self.db.collection("alerts").where("store_id", "==", store_id)

        all_transaction_docs = [doc async for doc in transactions_query.stream()]
        product_docs = [doc async for doc in products_query.stream()]
        alert_docs = [doc async for doc in alerts_query.stream()]

        transaction_docs = []
        for doc in all_transaction_docs:
            txn = doc.to_dict() or {}
            sale_timestamp = txn.get("sale_timestamp")
            if not isinstance(sale_timestamp, datetime):
                continue
            sale_dt = sale_timestamp.astimezone(timezone.utc)
            if start_of_day <= sale_dt < end_of_day:
                transaction_docs.append(doc)

        active_alert_docs = []
        for doc in alert_docs:
            alert = doc.to_dict() or {}
            if alert.get("status") == "ACTIVE":
                active_alert_docs.append(doc)

        today_sales = 0.0
        product_units_sold: dict[str, int] = defaultdict(int)
        product_name_by_id: dict[str, str] = {}

        for doc in transaction_docs:
            txn = doc.to_dict() or {}
            today_sales += float(txn.get("total_amount", 0.0))
            for item in txn.get("items", []):
                product_id = item.get("product_id")
                if not product_id:
                    continue
                product_units_sold[product_id] += int(item.get("quantity", 0))
                if item.get("product_name"):
                    product_name_by_id[product_id] = str(item["product_name"])

        low_stock_count = 0
        for doc in product_docs:
            product = doc.to_dict() or {}
            if product.get("status") == "INACTIVE":
                continue
            product_id = str(product.get("product_id") or doc.id)
            product_name_by_id.setdefault(product_id, str(product.get("name") or product_id))
            quantity_on_hand = int(product.get("quantity_on_hand", 0))
            reorder_threshold = int(product.get("reorder_threshold", 0))
            if quantity_on_hand <= reorder_threshold:
                low_stock_count += 1

        top_selling_product: Optional[str] = None
        if product_units_sold:
            top_product_id = max(
                product_units_sold.items(),
                key=lambda item: (item[1], product_name_by_id.get(item[0], item[0])),
            )[0]
            top_selling_product = product_name_by_id.get(top_product_id, top_product_id)

        return {
            "today_sales": round(today_sales, 2),
            "today_transactions": len(transaction_docs),
            "active_alert_count": len(active_alert_docs),
            "low_stock_count": low_stock_count,
            "top_selling_product": top_selling_product,
        }

    async def get_live_sales_trends(
        self,
        store_id: str,
        range_days: int = 30,
        granularity: str = "daily",
    ) -> List[Dict[str, Any]]:
        """
        Build sales trend points directly from Firestore transactions.

        This keeps analytics responsive immediately after billing writes.
        """
        now_utc = datetime.now(timezone.utc)
        start_boundary = (now_utc - timedelta(days=range_days - 1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        transactions_query = self.db.collection("transactions").where("store_id", "==", store_id)
        all_transaction_docs = [doc async for doc in transactions_query.stream()]

        buckets: dict[str, dict[str, Any]] = {}
        for doc in all_transaction_docs:
            txn = doc.to_dict() or {}
            sale_timestamp = txn.get("sale_timestamp")
            if not isinstance(sale_timestamp, datetime):
                continue

            sale_dt = sale_timestamp.astimezone(timezone.utc)
            if sale_dt < start_boundary:
                continue
            if granularity == "weekly":
                week_start = sale_dt.date() - timedelta(days=sale_dt.weekday())
                label = week_start.isoformat()
            else:
                label = sale_dt.date().isoformat()

            bucket = buckets.setdefault(
                label,
                {"label": label, "sales_amount": 0.0, "transactions": 0},
            )
            bucket["sales_amount"] += float(txn.get("total_amount", 0.0))
            bucket["transactions"] += 1

        return [
            {
                "label": label,
                "sales_amount": round(float(bucket["sales_amount"]), 2),
                "transactions": int(bucket["transactions"]),
            }
            for label, bucket in sorted(buckets.items(), key=lambda item: item[0])
        ]

    async def get_live_product_performance(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Build product performance directly from Firestore transactions.
        """
        transactions_query = self.db.collection("transactions").where("store_id", "==", store_id)
        transaction_docs = [doc async for doc in transactions_query.stream()]

        product_totals: dict[str, dict[str, Any]] = {}
        for doc in transaction_docs:
            txn = doc.to_dict() or {}
            for item in txn.get("items", []):
                product_id = item.get("product_id")
                if not product_id:
                    continue

                bucket = product_totals.setdefault(
                    str(product_id),
                    {
                        "product_id": str(product_id),
                        "product_name": str(item.get("product_name") or product_id),
                        "quantity_sold": 0,
                        "revenue": 0.0,
                    },
                )
                bucket["quantity_sold"] += int(item.get("quantity", 0))
                bucket["revenue"] += float(item.get("line_total", 0.0))

        ranked = sorted(
            product_totals.values(),
            key=lambda item: (-float(item["revenue"]), item["product_name"]),
        )
        return [
            {
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "quantity_sold": int(item["quantity_sold"]),
                "revenue": round(float(item["revenue"]), 2),
            }
            for item in ranked[:50]
        ]

    async def get_live_customer_insights(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Read customer rollups directly from Firestore.
        """
        customers_query = self.db.collection("customers").where("store_id", "==", store_id)
        customer_docs = [doc async for doc in customers_query.stream()]

        customers: list[dict[str, Any]] = []
        for doc in customer_docs:
            customer = doc.to_dict() or {}
            customers.append(
                {
                    "customer_id": str(customer.get("customer_id") or doc.id),
                    "name": str(customer.get("name") or "Unknown"),
                    "lifetime_spend": round(float(customer.get("total_spend", 0.0)), 2),
                    "visit_count": int(customer.get("visit_count", 0)),
                }
            )

        customers.sort(key=lambda item: (-float(item["lifetime_spend"]), item["name"]))
        return customers[:10]

    async def get_sales_trends(
        self,
        store_id: str,
        range_days: int = 30,
        granularity: str = "daily",
    ) -> List[Dict[str, Any]]:
        if granularity == "weekly":
            query = f"""
                SELECT
                    CAST(DATE_TRUNC(sales_date, WEEK(MONDAY)) AS STRING) AS label,
                    SUM(total_sales) AS sales_amount,
                    SUM(transaction_count) AS transactions
                FROM `{self.project}.{self.dataset_mart}.sales_daily`
                WHERE store_id = @store_id
                  AND sales_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @range_days DAY)
                GROUP BY label
                ORDER BY label DESC
            """
        else:
            query = f"""
                SELECT
                    CAST(sales_date AS STRING) AS label,
                    total_sales AS sales_amount,
                    transaction_count AS transactions
                FROM `{self.project}.{self.dataset_mart}.sales_daily`
                WHERE store_id = @store_id
                  AND sales_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @range_days DAY)
                ORDER BY sales_date DESC
            """
        params = [
            bigquery.ScalarQueryParameter("store_id", "STRING", store_id),
            bigquery.ScalarQueryParameter("range_days", "INT64", range_days),
        ]
        rows = await asyncio.to_thread(self._run_query, query, params)
        # Return ascending for charts
        formatted_rows = [
            {
                "label": row["label"],
                "sales_amount": float(row.get("sales_amount", 0.0)),
                "transactions": int(row.get("transactions", 0))
            }
            for row in rows
        ]
        return formatted_rows[::-1]

    async def get_product_performance(self, store_id: str) -> List[Dict[str, Any]]:
        query = f"""
            SELECT product_id, ANY_VALUE(product_name) as product_name, SUM(quantity_sold) as quantity_sold, SUM(revenue) as revenue
            FROM `{self.project}.{self.dataset_mart}.product_sales_daily`
            WHERE store_id = @store_id
            GROUP BY product_id
            ORDER BY revenue DESC
            LIMIT 50
        """
        params = [bigquery.ScalarQueryParameter("store_id", "STRING", store_id)]
        rows = await asyncio.to_thread(self._run_query, query, params)
        return [
            {
                "product_id": row["product_id"],
                "product_name": row.get("product_name", "Unknown"),
                "quantity_sold": int(row.get("quantity_sold", 0)),
                "revenue": float(row.get("revenue", 0.0))
            }
            for row in rows
        ]

    async def get_customer_insights(self, store_id: str) -> List[Dict[str, Any]]:
        query = f"""
            SELECT customer_id, customer_name as name, lifetime_spend, visit_count
            FROM `{self.project}.{self.dataset_mart}.customer_summary`
            WHERE store_id = @store_id
            ORDER BY lifetime_spend DESC
            LIMIT 10
        """
        params = [bigquery.ScalarQueryParameter("store_id", "STRING", store_id)]
        rows = await asyncio.to_thread(self._run_query, query, params)
        return [
            {
                "customer_id": row["customer_id"],
                "name": row.get("name", "Unknown"),
                "lifetime_spend": float(row.get("lifetime_spend", 0.0)),
                "visit_count": int(row.get("visit_count", 0))
            }
            for row in rows
        ]
