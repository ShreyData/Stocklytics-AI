from __future__ import annotations

from typing import Any

from google.cloud import firestore

from app.common.config import get_settings


class CustomerRepository:
    def __init__(self):
        # Keep repository construction import-safe by delaying client creation
        # until a database call is actually executed.
        self._settings = get_settings()
        self._db: firestore.AsyncClient | None = None

    def _get_db(self) -> firestore.AsyncClient:
        if self._db is None:
            project = self._settings.firestore_project_id or None
            self._db = firestore.AsyncClient(project=project)
        return self._db

    async def get_customer_by_id(self, customer_id: str) -> dict[str, Any] | None:
        """Fetch a single customer profile by their document ID."""
        db = self._get_db()
        doc_ref = db.collection("customers").document(customer_id)
        doc = await doc_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["customer_id"] = doc.id
            return data
        return None

    async def get_customer_by_phone(
        self,
        store_id: str,
        phone: str,
    ) -> dict[str, Any] | None:
        """Fetch a customer profile by phone for uniqueness checking."""
        db = self._get_db()
        query = (
            db.collection("customers")
            .where("store_id", "==", store_id)
            .where("phone", "==", phone)
            .limit(1)
        )
        docs = await query.get()
        if docs:
            data = docs[0].to_dict() or {}
            data["customer_id"] = docs[0].id
            return data
        return None

    async def create_customer(
        self,
        customer_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new customer profile."""
        db = self._get_db()
        doc_ref = db.collection("customers").document(customer_id)
        await doc_ref.set(data)
        response = dict(data)
        response["customer_id"] = customer_id
        return response

    async def list_customers(self, store_id: str) -> list[dict[str, Any]]:
        """List customers scoped to a store."""
        db = self._get_db()
        query = (
            db.collection("customers")
            .where("store_id", "==", store_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
        )
        docs = await query.get()
        results: list[dict[str, Any]] = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["customer_id"] = doc.id
            results.append(data)
        return results

    async def get_purchase_history(
        self,
        store_id: str,
        customer_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch a customer's purchase history from the transactions collection."""
        db = self._get_db()
        query = (
            db.collection("transactions")
            .where("store_id", "==", store_id)
            .where("customer_id", "==", customer_id)
            .order_by("sale_timestamp", direction=firestore.Query.DESCENDING)
        )
        docs = await query.get()
        results: list[dict[str, Any]] = []
        for doc in docs:
            data = doc.to_dict() or {}
            mapped_data = {
                "transaction_id": doc.id,
                "total_amount": data.get("total_amount", 0.0),
                "sale_timestamp": data.get("sale_timestamp"),
            }
            results.append(mapped_data)
        return results
