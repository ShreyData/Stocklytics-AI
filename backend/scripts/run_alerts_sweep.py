"""
Script to run scheduled alert evaluations (sweeps) across all products.

Can be triggered by Cloud Scheduler -> Cloud Run Jobs.
Usage:
    python -m scripts.run_alerts_sweep --sweep-type hourly
    python -m scripts.run_alerts_sweep --sweep-type daily
"""

import argparse
import asyncio
import logging
import sys

from google.cloud import firestore

from app.common.config import get_settings
from app.modules.alerts.engine import (
    evaluate_expiry_soon,
    evaluate_high_demand_for_store,
    evaluate_low_stock,
    evaluate_not_selling_for_store,
)

# Configure basic logging for the script
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("alerts_sweep")


async def get_all_products() -> list[dict]:
    """Fetch all products across all stores (or you could chunk by store)."""
    settings = get_settings()
    db = firestore.AsyncClient(project=settings.firestore_project_id or None)
    
    products = []
    # In a real large-scale system, this would use pagination or be scoped to active stores.
    # For now, we fetch all products.
    docs = db.collection("products").stream()
    async for doc in docs:
        data = doc.to_dict() or {}
        data.setdefault("product_id", doc.id)
        products.append(data)
    return products


async def run_hourly_sweep():
    """Evaluate LOW_STOCK conditions."""
    logger.info("Starting hourly LOW_STOCK sweep...")
    products = await get_all_products()
    
    for p in products:
        store_id = p.get("store_id")
        product_id = p.get("product_id")
        product_name = p.get("name", "Unknown Product")
        current_stock = int(p.get("quantity_on_hand", 0))
        reorder_threshold = int(p.get("reorder_threshold", 0))
        
        if not store_id or not product_id:
            continue
            
        await evaluate_low_stock(
            store_id=store_id,
            product_id=product_id,
            product_name=product_name,
            current_stock=current_stock,
            reorder_threshold=reorder_threshold
        )
    logger.info(f"Finished hourly sweep. Evaluated {len(products)} products.")


async def run_daily_sweep():
    """Evaluate EXPIRY_SOON conditions."""
    logger.info("Starting daily EXPIRY_SOON sweep...")
    products = await get_all_products()
    
    for p in products:
        store_id = p.get("store_id")
        product_id = p.get("product_id")
        product_name = p.get("name", "Unknown Product")
        current_stock = int(p.get("quantity_on_hand", 0))
        expiry_date = p.get("expiry_date")
        
        if not store_id or not product_id:
            continue
            
        await evaluate_expiry_soon(
            store_id=store_id,
            product_id=product_id,
            product_name=product_name,
            expiry_date=expiry_date,
            current_stock=current_stock
        )
    logger.info(f"Finished daily sweep. Evaluated {len(products)} products.")


async def run_not_selling_sweep():
    """Evaluate NOT_SELLING conditions per store."""
    logger.info("Starting daily NOT_SELLING sweep...")
    products = await get_all_products()
    store_ids = {str(p.get("store_id")) for p in products if p.get("store_id")}

    for store_id in store_ids:
        await evaluate_not_selling_for_store(store_id=store_id)

    logger.info(f"Finished NOT_SELLING sweep. Evaluated {len(store_ids)} stores.")


async def run_high_demand_sweep():
    """Evaluate HIGH_DEMAND conditions per store."""
    logger.info("Starting 15-minute HIGH_DEMAND sweep...")
    products = await get_all_products()
    store_ids = {str(p.get("store_id")) for p in products if p.get("store_id")}

    for store_id in store_ids:
        await evaluate_high_demand_for_store(store_id=store_id)

    logger.info(f"Finished HIGH_DEMAND sweep. Evaluated {len(store_ids)} stores.")


async def main():
    parser = argparse.ArgumentParser(description="Run Alerts Sweep")
    parser.add_argument(
        "--sweep-type",
        choices=["hourly", "daily", "not-selling", "high-demand"],
        required=True,
        help=(
            "Sweep to run: "
            "'hourly' (LOW_STOCK), "
            "'daily' (EXPIRY_SOON), "
            "'not-selling' (NOT_SELLING), "
            "'high-demand' (HIGH_DEMAND)."
        ),
    )
    args = parser.parse_args()

    try:
        if args.sweep_type == "hourly":
            await run_hourly_sweep()
        elif args.sweep_type == "daily":
            await run_daily_sweep()
        elif args.sweep_type == "not-selling":
            await run_not_selling_sweep()
        elif args.sweep_type == "high-demand":
            await run_high_demand_sweep()
    except Exception as e:
        logger.error(f"Sweep failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
