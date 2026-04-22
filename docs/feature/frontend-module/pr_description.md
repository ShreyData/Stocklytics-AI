# What does this PR do?

Integrates the foundational Frontend Module — restructuring the Next.js React application cleanly into the mono-repository, setting up a dual-mode API service architecture with proxy routing, and wiring the complete Inventory UI to real backend endpoints.

## Files Added/Modified

| File | Purpose |
|---|---|
| `docs/feature/frontend-module/*` | Frontend implementation specs, plans, completion logs, and remaining tasks |
| `frontend/next.config.ts` | Next.js configuration including the API rewrite proxy rule (`/api/v1/*` → `localhost:8000`) |
| `frontend/lib/api.ts` | Shared Axios client with SSR-safe `dev-token` injection and standardized 404/payload error handling |
| `frontend/lib/api-service.ts` | Dual-mode data service. Routes Inventory calls to real APIs. Injects fallback proxy mock payloads for stubbed modules |
| `frontend/lib/types.ts` | End-to-end interface parity syncing frontend arrays perfectly with backend Pydantic Schemas |
| `frontend/app/inventory/page.tsx` | Interactive React layout integrating fully responsive `Add Product`, `Edit`, and `Stock Adjust` modal dialogues |
| `frontend/components/auth-provider.tsx` | Context provider automatically populating `dev-token` auth headers mapping to local environment backend bypass tools |

## Technical Implementation Rules Enforced

- **Clean Repo Structure** — Nested git instances imported from external scaffolding (AI Studio artifacts) are eliminated. The Next.js standard directory seamlessly interfaces with the mono-repository.
- **Strict API Proxy** — Raw URL CORS configuration eliminated; the frontend transparently rewrites proxy payload fetches to the FastAPI upstream dynamically mapped by the runtime `.env`.
- **Idempotent Dual-Mode State** — Allows parallel system engineering. Implemented modules (Inventory) automatically route down to the real `uvicorn` layer. Pending stub routes (Alerts, Analytics) silently handle UI state utilizing intelligent fallback local data.
- **Typing Integrity** — Types manually mirrored down to granular `ProductUpdateRequest` and `StockAdjustmentRequest` fields ensuring UI components cannot pass payloads failing Python Pydantic assertions.
- **Dynamic Local Auth** — Local testing context correctly populates and mounts internal Next.js node-contexts with the standard default `dev-token`.

## Tests & Verification

| Check | Coverage |
|---|---|
| **Directory Restructure Check** | 100% flat app/ tree integration; isolated `.git`, placeholder, and `AI Studio` artifacts discarded entirely. |
| **Routing / Proxy Proxy Check** | Passes `http://localhost:3000/api/v1/health` test forwarding down to port 8000. |
| **API Integration (Inventory)** | Create, View, Handle Edit, and Stock Adjust visually verified end-to-end pushing correct `quantity_delta` schemas without console errors. |
| **TypeScript Strict Analysis** | Clean zero-emission `tsc` compile. `interface` bounds rigorously respected across API models. |
