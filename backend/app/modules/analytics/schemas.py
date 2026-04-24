from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class DashboardSummaryItem(BaseModel):
    today_sales: float
    today_transactions: int
    active_alert_count: int
    low_stock_count: int
    top_selling_product: Optional[str] = None

class SalesTrendPoint(BaseModel):
    label: str
    sales_amount: float
    transactions: int

class ProductPerformanceItem(BaseModel):
    product_id: str
    product_name: str
    quantity_sold: int
    revenue: float

class CustomerInsightItem(BaseModel):
    customer_id: str
    name: str
    lifetime_spend: float
    visit_count: int
