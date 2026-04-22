# Phase 2: Frontend Module - Remaining Work

This document outlines the pending work required to complete the `feature/frontend-module` integration phase.

## Complete Frontend/Backend Integration is Pending

While the API foundations, proxy, and Inventory module have been strictly connected, the comprehensive frontend and backend integration remains pending. 

### Pending Integration Details:
- **Billing Module Webhooks**: The frontend currently relies on mock data for the billing cart. The `api-service.ts` needs to be updated to point to `/api/v1/billing` endpoints to process transactions with proper `idempotency_key` headers once the backend billing router is implemented.
- **Customers & Analytics**: Real-time sales charts and customer purchase histories must be wired to the respective BigQuery mart tables APIs. The frontend currently mocks freshness indicators.
- **Alerts Lifecycle**: The active alerts summary and resolution actions (`acknowledge`, `resolve`) are waiting for the backend Firestore triggers to be completed.
- **AI Chat Grounding**: The AI assistant chat page is currently stubbed. It must be connected to `/api/v1/ai/chat` to provide fully grounded answers based on live storefront analytics.
- **E2E Testing**: A complete end-to-end user browser test ensuring state is perfectly synced from the frontend UI layers all the way down to BigQuery/Firestore needs to be conducted.
