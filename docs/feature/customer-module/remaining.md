# Customer Module - Remaining Tasks

This document tracks the tasks that are still left to be completed for the Customer Module.

## Pending Items
- **Customer-Specific Tests**: Write unit/integration tests for the customer module (`tests/test_customer.py`), covering:
  - Happy path for create, list, detail, and purchase history.
  - Duplicate customer handling.
  - Store-scope protection.
  - Not found handling.
- **Billing Integration**: Implement or verify the billing-to-customer summary updates. Ensure that successful `COMPLETED` transactions from the Billing module atomic write path update the `total_spend`, `visit_count`, and `last_purchase_at` fields on the customer profile securely without violating idempotency.
