from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CustomerCreateRequest(BaseModel):
    store_id: str = Field(..., description="The store ID this customer belongs to")
    name: str = Field(..., description="Customer's full name")
    phone: str = Field(..., description="Customer's phone number")


class Customer(BaseModel):
    customer_id: str
    store_id: str
    name: str
    phone: str
    total_spend: float = 0.0
    visit_count: int = 0
    last_purchase_at: Optional[datetime] = None


class CustomerListItem(BaseModel):
    customer_id: str
    name: str
    phone: str
    total_spend: float
    visit_count: int
    last_purchase_at: Optional[datetime] = None


class CustomerResponse(BaseModel):
    # Enveloped in success_response, the actual 'customer' field is returned
    customer: Customer


class CustomerListResponse(BaseModel):
    items: List[CustomerListItem]


class TransactionHistoryItem(BaseModel):
    transaction_id: str
    total_amount: float
    sale_timestamp: datetime


class PurchaseHistoryResponse(BaseModel):
    customer_id: str
    transactions: List[TransactionHistoryItem]
