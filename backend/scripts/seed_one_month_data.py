"""
Seed Script – Populate Firestore with 1 Month of General Store Data.

Generates realistic Indian general-store data for testing AI, Analytics,
Dashboard, Alerts, and Data-Pipeline modules.

Collections written:
    products           – ~50 general store products (INR prices)
    customers          – ~20 customer profiles
    transactions       – ~500+ transactions over the past 30 days
    stock_adjustments  – stock adjustment audit entries

Usage:
    python -m scripts.seed_one_month_data [--store-id STORE_ID] [--clear]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.common.config import get_settings, setup_logging
from app.common.google_clients import create_firestore_async_client

setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Product catalog – Indian general store items
# ---------------------------------------------------------------------------

PRODUCTS_CATALOG = [
    # Groceries / Staples
    {"name": "Tata Salt 1kg", "category": "Groceries", "price": 28.0, "reorder": 20, "expiry_days": 365},
    {"name": "Aashirvaad Atta 5kg", "category": "Groceries", "price": 295.0, "reorder": 8, "expiry_days": 180},
    {"name": "Fortune Sunflower Oil 1L", "category": "Groceries", "price": 155.0, "reorder": 10, "expiry_days": 270},
    {"name": "India Gate Basmati Rice 5kg", "category": "Groceries", "price": 425.0, "reorder": 6, "expiry_days": 365},
    {"name": "Toor Dal 1kg", "category": "Groceries", "price": 145.0, "reorder": 12, "expiry_days": 240},
    {"name": "Sugar 1kg", "category": "Groceries", "price": 48.0, "reorder": 15, "expiry_days": 365},
    {"name": "MDH Garam Masala 100g", "category": "Groceries", "price": 72.0, "reorder": 10, "expiry_days": 300},
    {"name": "Everest Turmeric Powder 200g", "category": "Groceries", "price": 55.0, "reorder": 10, "expiry_days": 300},
    {"name": "Rajma 1kg", "category": "Groceries", "price": 160.0, "reorder": 8, "expiry_days": 240},
    {"name": "Moong Dal 1kg", "category": "Groceries", "price": 135.0, "reorder": 10, "expiry_days": 240},

    # Dairy
    {"name": "Amul Butter 500g", "category": "Dairy", "price": 270.0, "reorder": 8, "expiry_days": 60},
    {"name": "Mother Dairy Milk 1L", "category": "Dairy", "price": 64.0, "reorder": 20, "expiry_days": 5},
    {"name": "Amul Cheese Slice 200g", "category": "Dairy", "price": 115.0, "reorder": 6, "expiry_days": 90},
    {"name": "Dahi 400g", "category": "Dairy", "price": 35.0, "reorder": 15, "expiry_days": 7},
    {"name": "Amul Paneer 200g", "category": "Dairy", "price": 90.0, "reorder": 8, "expiry_days": 10},

    # Snacks
    {"name": "Lays Classic Salted 52g", "category": "Snacks", "price": 20.0, "reorder": 25, "expiry_days": 120},
    {"name": "Parle-G Biscuit 800g", "category": "Snacks", "price": 80.0, "reorder": 15, "expiry_days": 180},
    {"name": "Haldiram Namkeen Bhujia 200g", "category": "Snacks", "price": 65.0, "reorder": 12, "expiry_days": 150},
    {"name": "Britannia Good Day 250g", "category": "Snacks", "price": 45.0, "reorder": 15, "expiry_days": 180},
    {"name": "Kurkure Masala Munch 90g", "category": "Snacks", "price": 20.0, "reorder": 25, "expiry_days": 120},
    {"name": "Dark Fantasy Choco Fills 75g", "category": "Snacks", "price": 40.0, "reorder": 12, "expiry_days": 150},

    # Beverages
    {"name": "Coca-Cola 750ml", "category": "Beverages", "price": 40.0, "reorder": 20, "expiry_days": 180},
    {"name": "Tata Tea Gold 500g", "category": "Beverages", "price": 265.0, "reorder": 8, "expiry_days": 365},
    {"name": "Nescafe Classic 50g", "category": "Beverages", "price": 165.0, "reorder": 6, "expiry_days": 365},
    {"name": "Real Mango Juice 1L", "category": "Beverages", "price": 99.0, "reorder": 10, "expiry_days": 180},
    {"name": "Bisleri Water 1L", "category": "Beverages", "price": 20.0, "reorder": 30, "expiry_days": 365},
    {"name": "Thumbs Up 750ml", "category": "Beverages", "price": 40.0, "reorder": 20, "expiry_days": 180},

    # Personal Care
    {"name": "Dove Soap 100g", "category": "Personal Care", "price": 52.0, "reorder": 15, "expiry_days": 730},
    {"name": "Colgate MaxFresh 150g", "category": "Personal Care", "price": 95.0, "reorder": 10, "expiry_days": 730},
    {"name": "Head & Shoulders Shampoo 180ml", "category": "Personal Care", "price": 195.0, "reorder": 6, "expiry_days": 730},
    {"name": "Dettol Handwash 200ml", "category": "Personal Care", "price": 55.0, "reorder": 10, "expiry_days": 730},
    {"name": "Nivea Body Lotion 200ml", "category": "Personal Care", "price": 215.0, "reorder": 5, "expiry_days": 730},

    # Household
    {"name": "Vim Dishwash Bar 300g", "category": "Household", "price": 30.0, "reorder": 15, "expiry_days": 730},
    {"name": "Surf Excel Matic 1kg", "category": "Household", "price": 299.0, "reorder": 6, "expiry_days": 730},
    {"name": "Harpic Toilet Cleaner 500ml", "category": "Household", "price": 89.0, "reorder": 8, "expiry_days": 730},
    {"name": "Lizol Floor Cleaner 500ml", "category": "Household", "price": 115.0, "reorder": 8, "expiry_days": 730},
    {"name": "Garbage Bags Pack of 30", "category": "Household", "price": 60.0, "reorder": 10, "expiry_days": None},

    # Instant / Ready-to-eat
    {"name": "Maggi 2-Minute Noodles 4-pack", "category": "Instant Food", "price": 56.0, "reorder": 20, "expiry_days": 240},
    {"name": "MTR Ready-to-Eat Poha", "category": "Instant Food", "price": 55.0, "reorder": 8, "expiry_days": 180},
    {"name": "Knorr Tomato Soup 53g", "category": "Instant Food", "price": 40.0, "reorder": 10, "expiry_days": 240},
    {"name": "Ching's Schezwan Noodles", "category": "Instant Food", "price": 25.0, "reorder": 15, "expiry_days": 240},
    {"name": "Saffola Oats 1kg", "category": "Instant Food", "price": 165.0, "reorder": 6, "expiry_days": 270},

    # Confectionery / Sweets
    {"name": "Cadbury Dairy Milk 50g", "category": "Confectionery", "price": 50.0, "reorder": 20, "expiry_days": 270},
    {"name": "KitKat 37.3g", "category": "Confectionery", "price": 30.0, "reorder": 20, "expiry_days": 270},
    {"name": "5 Star 40g", "category": "Confectionery", "price": 30.0, "reorder": 20, "expiry_days": 270},
    {"name": "Mentos Roll", "category": "Confectionery", "price": 10.0, "reorder": 30, "expiry_days": 365},
    {"name": "Pulse Candy Pack", "category": "Confectionery", "price": 10.0, "reorder": 30, "expiry_days": 365},
    {"name": "Gems 17.8g", "category": "Confectionery", "price": 10.0, "reorder": 30, "expiry_days": 270},

    # Eggs & Bread
    {"name": "Farm Eggs (12 pack)", "category": "Eggs & Bread", "price": 84.0, "reorder": 10, "expiry_days": 14},
    {"name": "Britannia Bread 400g", "category": "Eggs & Bread", "price": 40.0, "reorder": 10, "expiry_days": 5},
]

# ---------------------------------------------------------------------------
# Customer names – Indian context
# ---------------------------------------------------------------------------

CUSTOMER_NAMES = [
    ("Rajesh Kumar", "+919876543210"),
    ("Priya Sharma", "+919876543211"),
    ("Amit Patel", "+919876543212"),
    ("Sunita Verma", "+919876543213"),
    ("Vikas Gupta", "+919876543214"),
    ("Neha Singh", "+919876543215"),
    ("Deepak Joshi", "+919876543216"),
    ("Anita Rao", "+919876543217"),
    ("Manoj Tiwari", "+919876543218"),
    ("Kavita Mishra", "+919876543219"),
    ("Ramesh Yadav", "+919876543220"),
    ("Pooja Agarwal", "+919876543221"),
    ("Suresh Reddy", "+919876543222"),
    ("Meena Iyer", "+919876543223"),
    ("Arun Nair", "+919876543224"),
    ("Rekha Pandey", "+919876543225"),
    ("Sanjay Mehta", "+919876543226"),
    ("Divya Saxena", "+919876543227"),
    ("Harish Chauhan", "+919876543228"),
    ("Lata Deshmukh", "+919876543229"),
]


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _random_time_in_day(day: datetime) -> datetime:
    """Return a random time between 8 AM and 10 PM on the given day."""
    hour = random.randint(8, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------

async def seed(store_id: str, clear_existing: bool = False) -> None:
    settings = get_settings()
    project = settings.firestore_project_id or None
    db = create_firestore_async_client(project=project)

    now = datetime.now(timezone.utc)
    one_month_ago = now - timedelta(days=30)

    # -----------------------------------------------------------------------
    # 0) Optionally clear existing data for this store
    # -----------------------------------------------------------------------
    if clear_existing:
        logger.info("Clearing existing data for store %s …", store_id)
        for coll in ("products", "stock_adjustments", "transactions", "customers", "alerts"):
            query = db.collection(coll).where("store_id", "==", store_id)
            batch_count = 0
            async for doc in query.stream():
                await doc.reference.delete()
                batch_count += 1
            logger.info("  Deleted %d docs from '%s'", batch_count, coll)

    # -----------------------------------------------------------------------
    # 1) Seed products
    # -----------------------------------------------------------------------
    logger.info("Seeding %d products …", len(PRODUCTS_CATALOG))
    product_docs: list[dict] = []

    for idx, item in enumerate(PRODUCTS_CATALOG):
        product_id = _uid("prod_")
        created_at = one_month_ago - timedelta(days=random.randint(1, 10))
        quantity = random.randint(item["reorder"] + 5, item["reorder"] * 4 + 20)

        expiry_date = None
        if item["expiry_days"] is not None:
            expiry_date = now + timedelta(days=item["expiry_days"] - random.randint(0, item["expiry_days"] // 2))

        # Determine expiry_status
        expiry_status = "OK"
        if expiry_date:
            days_left = (expiry_date - now).days
            if days_left <= 0:
                expiry_status = "EXPIRED"
            elif days_left <= 7:
                expiry_status = "EXPIRING_SOON"

        doc = {
            "product_id": product_id,
            "store_id": store_id,
            "name": item["name"],
            "category": item["category"],
            "price": item["price"],
            "quantity_on_hand": quantity,
            "reorder_threshold": item["reorder"],
            "expiry_date": expiry_date,
            "expiry_status": expiry_status,
            "status": "ACTIVE",
            "created_at": created_at,
            "updated_at": now - timedelta(minutes=random.randint(5, 1440)),
        }
        product_docs.append(doc)
        await db.collection("products").document(product_id).set(doc)

    logger.info("✓ Seeded %d products", len(product_docs))

    # -----------------------------------------------------------------------
    # 2) Seed customers
    # -----------------------------------------------------------------------
    logger.info("Seeding %d customers …", len(CUSTOMER_NAMES))
    customer_docs: list[dict] = []

    for name, phone in CUSTOMER_NAMES:
        customer_id = _uid("cust_")
        created_at = one_month_ago - timedelta(days=random.randint(1, 30))

        doc = {
            "customer_id": customer_id,
            "store_id": store_id,
            "name": name,
            "phone": phone,
            "total_spend": 0.0,
            "visit_count": 0,
            "last_purchase_at": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        customer_docs.append(doc)
        await db.collection("customers").document(customer_id).set(doc)

    logger.info("✓ Seeded %d customers", len(customer_docs))

    # -----------------------------------------------------------------------
    # 3) Seed transactions over 30 days
    # -----------------------------------------------------------------------
    # Generate 10-25 transactions per day (realistic for a small store)
    logger.info("Generating transactions for the past 30 days …")

    payment_methods = ["cash", "upi", "card"]
    payment_weights = [0.4, 0.45, 0.15]  # UPI heavy – very common in India now

    total_transactions = 0
    total_items = 0
    all_adjustments: list[dict] = []

    for day_offset in range(30, -1, -1):
        day = now - timedelta(days=day_offset)
        # Weekends get more traffic
        is_weekend = day.weekday() in (5, 6)
        num_transactions = random.randint(14, 28) if is_weekend else random.randint(10, 22)

        for _ in range(num_transactions):
            txn_time = _random_time_in_day(day)
            txn_id = _uid("txn_")

            # Pick 1-6 random products for this transaction
            num_items = random.choices([1, 2, 3, 4, 5, 6], weights=[15, 30, 25, 15, 10, 5])[0]
            selected_products = random.sample(product_docs, min(num_items, len(product_docs)))

            items = []
            txn_total = 0.0

            for prod in selected_products:
                qty = random.randint(1, 3)
                unit_price = prod["price"]
                line_total = round(unit_price * qty, 2)
                txn_total += line_total

                items.append({
                    "product_id": prod["product_id"],
                    "product_name": prod["name"],
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                })

                # Create a stock adjustment for each sale
                adj_id = _uid("adj_")
                adj_doc = {
                    "adjustment_id": adj_id,
                    "store_id": store_id,
                    "product_id": prod["product_id"],
                    "adjustment_type": "SALE_DEDUCTION",
                    "quantity_delta": qty,
                    "reason": f"Billing transaction {txn_id}",
                    "source_ref": txn_id,
                    "created_by": "billing_service",
                    "created_at": txn_time,
                }
                all_adjustments.append(adj_doc)

            # Assign customer to ~60% of transactions
            customer_id = None
            if random.random() < 0.6 and customer_docs:
                customer = random.choice(customer_docs)
                customer_id = customer["customer_id"]
                # Update running totals in-memory
                customer["total_spend"] = round(customer["total_spend"] + txn_total, 2)
                customer["visit_count"] += 1
                customer["last_purchase_at"] = txn_time
                customer["updated_at"] = txn_time

            payment_method = random.choices(payment_methods, weights=payment_weights)[0]
            idempotency_key = str(uuid.uuid4())

            txn_doc = {
                "transaction_id": txn_id,
                "store_id": store_id,
                "customer_id": customer_id,
                "idempotency_key": idempotency_key,
                "total_amount": round(txn_total, 2),
                "payment_method": payment_method,
                "status": "COMPLETED",
                "sale_timestamp": txn_time,
                "created_at": txn_time,
                "items": items,
            }

            await db.collection("transactions").document(txn_id).set(txn_doc)
            total_transactions += 1
            total_items += len(items)

    logger.info("✓ Seeded %d transactions with %d line items", total_transactions, total_items)

    # -----------------------------------------------------------------------
    # 4) Write stock adjustments
    # -----------------------------------------------------------------------
    logger.info("Writing %d stock adjustments …", len(all_adjustments))
    for adj in all_adjustments:
        await db.collection("stock_adjustments").document(adj["adjustment_id"]).set(adj)
    logger.info("✓ Seeded %d stock adjustments", len(all_adjustments))

    # -----------------------------------------------------------------------
    # 5) Update customer docs with accumulated totals
    # -----------------------------------------------------------------------
    logger.info("Updating customer totals …")
    for cust in customer_docs:
        await db.collection("customers").document(cust["customer_id"]).update({
            "total_spend": cust["total_spend"],
            "visit_count": cust["visit_count"],
            "last_purchase_at": cust["last_purchase_at"],
            "updated_at": cust["updated_at"] or now,
        })
    logger.info("✓ Updated %d customer profiles", len(customer_docs))

    # -----------------------------------------------------------------------
    # 6) Add a few restock adjustments (ADD) spread through the month
    # -----------------------------------------------------------------------
    logger.info("Adding restock adjustments …")
    restock_count = 0
    for prod in product_docs:
        # Each product gets 1-3 restocks during the month
        num_restocks = random.randint(1, 3)
        for _ in range(num_restocks):
            restock_day = one_month_ago + timedelta(days=random.randint(0, 29))
            restock_time = _random_time_in_day(restock_day)
            adj_id = _uid("adj_")
            restock_qty = random.randint(10, 50)

            adj_doc = {
                "adjustment_id": adj_id,
                "store_id": store_id,
                "product_id": prod["product_id"],
                "adjustment_type": "ADD",
                "quantity_delta": restock_qty,
                "reason": "Supplier restock",
                "source_ref": None,
                "created_by": "store_owner",
                "created_at": restock_time,
            }
            await db.collection("stock_adjustments").document(adj_id).set(adj_doc)
            restock_count += 1

    logger.info("✓ Seeded %d restock adjustments", restock_count)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("SEED COMPLETE for store_id=%s", store_id)
    logger.info("  Products:           %d", len(product_docs))
    logger.info("  Customers:          %d", len(customer_docs))
    logger.info("  Transactions:       %d", total_transactions)
    logger.info("  Line Items:         %d", total_items)
    logger.info("  Sale Adjustments:   %d", len(all_adjustments))
    logger.info("  Restock Adjustments:%d", restock_count)
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed 1 month of general store data into Firestore.")
    parser.add_argument(
        "--store-id",
        default="store_001",
        help="The store_id to seed data for (default: store_001).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data for this store before seeding.",
    )
    args = parser.parse_args()

    logger.info("Starting seed for store_id=%s (clear=%s)", args.store_id, args.clear)
    asyncio.run(seed(args.store_id, clear_existing=args.clear))


if __name__ == "__main__":
    main()
