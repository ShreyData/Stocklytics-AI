from typing import Any, Dict, List, Optional

from google.cloud import firestore

from app.common.config import get_settings


class CustomerRepository:
    def __init__(self):
        settings = get_settings()
        # Initialize Google Cloud Firestore AsyncClient
        # Falls back to application default credentials if not specifically configured with GOOGLE_APPLICATION_CREDENTIALS
        self.db = firestore.AsyncClient(project=settings.firestore_project_id)

    async def get_customer_by_id(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single customer profile by their document ID."""
        doc_ref = self.db.collection("customers").document(customer_id)
        doc = await doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            data["customer_id"] = doc.id
            return data
        return None

    async def get_customer_by_phone(self, store_id: str, phone: str) -> Optional[Dict[str, Any]]:
        """Fetch a customer profile by phone for uniqueness checking."""
        query = (
            self.db.collection("customers")
            .where("store_id", "==", store_id)
            .where("phone", "==", phone)
            .limit(1)
        )
        docs = await query.get()
        if docs:
            data = docs[0].to_dict()
            data["customer_id"] = docs[0].id
            return data
        return None

    async def create_customer(self, customer_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new customer profile."""
        doc_ref = self.db.collection("customers").document(customer_id)
        await doc_ref.set(data)
        data["customer_id"] = customer_id
        return data

    async def list_customers(self, store_id: str) -> List[Dict[str, Any]]:
        """List customers scoped to a store."""
        query = (
            self.db.collection("customers")
            .where("store_id", "==", store_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
        )
        docs = await query.get()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["customer_id"] = doc.id
            results.append(data)
        return results

    async def get_purchase_history(self, store_id: str, customer_id: str) -> List[Dict[str, Any]]:
        """Fetch a customer's purchase history from the transactions collection."""
        query = (
            self.db.collection("transactions")
            .where("store_id", "==", store_id)
            .where("customer_id", "==", customer_id)
            .order_by("sale_timestamp", direction=firestore.Query.DESCENDING)
        )
        docs = await query.get()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["transaction_id"] = doc.id
            results.append(data)
        return results
