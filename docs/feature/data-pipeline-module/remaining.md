# Remaining Tasks: Data Pipeline Module

All code for the `data_pipeline` module has been implemented according to the design docs, including:
- Data Pipeline schemas
- Firestore repository for checkpoints and failures
- Checkpoint manager (incremental logic)
- Failure handler (3-retry backoff)
- BigQuery loader (raw tables upsert)
- Mart transform (mart tables refresh via SQL)
- Runners (Sync, Transform, Repair)
- API Router
- Cloud Run Job entrypoints

## Cross-Module Dependencies Satisfied
- Verified `app/common/exceptions.py` uses correct HTTP exceptions.
- Verified `app/common/responses.py` handles consistent JSON payload mapping.
- Verified `app/common/auth.py` role dependencies are integrated via `require_auth` and `require_admin`.

## Pending Integrations
- Testing: Added `backend/tests/test_data_pipeline.py` and `backend/tests/test_data_pipeline_e2e.py` for retries, checkpoint behavior, trigger flow, and API error paths.
- BigQuery Setup: Project infrastructure needs actual BigQuery datasets `retailmind_raw` and `retailmind_mart` initialized in GCP to test the DML queries directly.

## Deployment Notes
Cloud Run Jobs must be deployed via Terraform/gcloud targeting the scripts:
- `python -m scripts.run_sync_job`
- `python -m scripts.run_transform_job`
- `python -m scripts.run_repair_job`
