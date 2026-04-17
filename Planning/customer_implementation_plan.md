# Implement Customer Module

Provide the implementation for the Customer Module to manage customer records and expose customer-wise sales history, strictly following the `customer_implementation.md`, `api_contracts.md`, and `database_design.md` specifications.

## User Review Required

> [!IMPORTANT]
> The database access layer uses `google.cloud.firestore.AsyncClient` by default for performance in FastAPI. Ensure your environment has the `GOOGLE_APPLICATION_CREDENTIALS` configured pointing to your Firebase/GCP credentials, or it will fall back to application default credentials.

## Proposed Changes

### `backend/app/modules/customer`

The following files will be added or modified in the Customer module:

#### [NEW] `schemas.py`
Pydantic schemas for the customer module payload validations.
- `CustomerCreateRequest` (name, phone)
- `CustomerResponse`
- `CustomerListResponse`
- `PurchaseHistoryResponse`

#### [NEW] `repository.py`
Data access layer interacting with Firestore.
- Method `get_customer(store_id, customer_id)`
- Method `create_customer(customer_data)`
- Method `list_customers(store_id)`
- Method `get_purchase_history(store_id, customer_id)`

#### [NEW] `service.py`
Business logic layer.
- Ensure isolation of validation logic from the endpoints.
- E.g. retrieving purchase history relies heavily on the `transactions` collection; this service acts as the orchestrator to fetch those transactions.

#### [MODIFY] `router.py`
Expose the REST API endpoints structured according to `api_contracts.md`.
- `POST /api/v1/customers`
- `GET /api/v1/customers`
- `GET /api/v1/customers/{customer_id}`
- `GET /api/v1/customers/{customer_id}/purchase-history`

## Open Questions

- Should we strictly enforce unique phone numbers per `store_id` during customer creation, or leave it lenient given it's described as "unique per store if used"? I will enforce unique phone checks if a phone number is provided to comply with standard customer module practices.

## Verification Plan

### Automated Tests
- Create Python units using `pytest` inside the `backend/tests/` folder if applicable, testing business logic behavior in `service.py`.

### Manual Verification
- Test all four endpoints by mocking fake auth payload or running with local Firebase emulator payload.
- Ensure Firestore collections are created in the appropriate data shape.
