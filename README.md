# Stocklytics AI

Modular monolith backend with a lightweight frontend for small retail stores.

## Structure
- `backend/` FastAPI services and modules
- `frontend/` Web UI
- `docs/` Project docs (code-facing)
- `infra/` Infrastructure and deployment assets
- `scripts/` Local tooling and helpers

## Notes
- Planning docs live in the `Plan/` folder and are ignored by Git.
- Cloud Run deployment templates live in `infra/cloudrun/`.
- Local secret files such as `.env`, `.env.local`, and Cloud Run env yaml files are intentionally ignored.


# Local backend docker running command
docker run --rm -p 8000:8080 --env-file ./infra/cloudrun/backend.env.yaml stocklytics-backend
# Local frontend docker running command
docker run --rm -p 3000:8080 --env-file ./infra/cloudrun/frontend.env.yaml stocklytics-frontend
