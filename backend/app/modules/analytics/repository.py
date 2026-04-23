import asyncio
from typing import Any, Dict, List, Optional
from google.cloud import bigquery, firestore
from app.common.config import get_settings

class AnalyticsRepository:
    def __init__(self):
        settings = get_settings()
        self.db = firestore.AsyncClient(project=settings.firestore_project_id)
        self.bq = bigquery.Client(project=settings.bigquery_project_id)
        self.dataset = settings.bigquery_dataset_mart
        self.project = settings.bigquery_project_id

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
            SELECT today_sales, today_transactions, active_alert_count, low_stock_count, top_selling_product
            FROM `{self.project}.{self.dataset}.dashboard_summary`
            WHERE store_id = @store_id
            ORDER BY snapshot_date DESC
            LIMIT 1
        """
        params = [bigquery.ScalarQueryParameter("store_id", "STRING", store_id)]
        rows = await asyncio.to_thread(self._run_query, query, params)
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

    async def get_sales_trends(self, store_id: str) -> List[Dict[str, Any]]:
        query = f"""
            SELECT CAST(sales_date AS STRING) as label, total_sales as sales_amount, transaction_count as transactions
            FROM `{self.project}.{self.dataset}.sales_daily`
            WHERE store_id = @store_id
            ORDER BY sales_date DESC
            LIMIT 30
        """
        params = [bigquery.ScalarQueryParameter("store_id", "STRING", store_id)]
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
            FROM `{self.project}.{self.dataset}.product_sales_daily`
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
            FROM `{self.project}.{self.dataset}.customer_summary`
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
