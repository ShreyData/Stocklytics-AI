# Phase 1: API Foundation - Remaining Work

This document tracks what remains incomplete within the API Foundation requirements and maps when to implement these items according to the project's workflow and roadmap.

## Unfinished Platform Dependencies
While the framework and API responses are fully configured, the real connection clients are currently stubbed.

1. **Firestore Client Definition**
2. **BigQuery Client Definition**
3. **Gemini Initialization**

### Action Items
- Replace `_probe_firestore()`, `_probe_bigquery()`, and `_probe_gemini()` in `app/api/platform.py` with actual connection ping logic.
- Create singletons or dependency injection structures in `common/` for standardizing database/model access.

## When to Implement (Per Project Workflow)

### 1. Merge API Foundation
According to `Plan/github_workflow_for_team.pdf` (**Merge Order**) and the `implementation_roadmap.md`, the current `feature/api-foundation` branch successfully completes Exit Criteria 1 and 2:
> * Health and readiness endpoints work
> * Authenticated requests reach module routers

**Immediate Next Step:** Open a PR for `feature/api-foundation` and merge it strictly into `main` *as is*, because PRs should be kept "focused and small" and not mix unrelated changes.

### 2. Follow-up Client Implementation
The actual client integrations must be implemented either:
- As mini-technical PRs branching off `main` before Phase 2.
- Immediately during the start of **Phase 2 (Inventory + Atomic Billing)**, via branch `feature/inventory-module`, since this is the first feature to actively require a real Firestore database connection.

### 3. Populating Secrets
Before local environments can use actual clients, the `.env` file must be populated with actual GCP and Firebase JSON credentials by the technical lead.
