# Customer Module Implementation

## 1. Module Goal
- Build the Customer Module that stores customer profiles and exposes customer-wise sales history.

## 2. Key Responsibilities
- Create and update customer records
- Track purchase history linked from transactions
- Maintain customer summary data like total spend and visit count
- Return top-customer and purchase-history data to Analytics and AI

## 3. Inputs
- Customer details:
  - `store_id`
  - `name`
  - `phone`
- Billing-linked customer transactions

## 4. Outputs
- Customer profile
- Customer list
- Purchase history
- Customer summary metrics

## 5. API Endpoints
- `POST /api/v1/customers`
- `GET /api/v1/customers`
- `GET /api/v1/customers/{customer_id}`
- `GET /api/v1/customers/{customer_id}/purchase-history`

## 6. Internal Flow
1. Validate auth, `store_id`, and customer payload.
2. Create or update customer record in Firestore `customers`.
3. When Billing writes a transaction with `customer_id`:
   - link the transaction to that customer
   - update `total_spend`
   - update `visit_count`
   - update `last_purchase_at`
4. For purchase history:
   - fetch transactions filtered by `customer_id`
   - return sorted history

## 7. Dependencies
- Firestore `customers`
- Firestore `transactions`
- Billing Module provides linked sales
- Analytics and AI consume customer summaries

## 8. Important Rules
- Customer is optional in billing, so this module must handle missing customer links cleanly.
- Keep `store_id` on all customer records.
- Do not duplicate detailed transaction data inside the customer document.
- Purchase history should come from transactions, not from copied arrays in the customer record.

## 9. Implementation Notes
- Keep customer data simple for MVP.
- Use the customer document for summary state, not for storing every purchase event.
- Follow `api_contracts.md`, `database_design.md`, and `module_breakdown.md`.
