# Cloud Run Deployment

Stocklytics is best deployed as two Cloud Run services:

- `stocklytics-backend`: FastAPI API
- `stocklytics-frontend`: Next.js standalone web app

## 1. Prerequisites

- Enable APIs:
  - Cloud Run Admin API
  - Cloud Build API
  - Artifact Registry API
  - Firestore API
  - BigQuery API
  - Secret Manager API
  - Firebase Management / Identity Toolkit as needed for auth
- Create an Artifact Registry repo, for example `stocklytics`.
- Create a dedicated Cloud Run service account for the backend.

Recommended backend service-account roles:

- `roles/datastore.user`
- `roles/bigquery.user`
- `roles/bigquery.dataViewer`
- `roles/bigquery.jobUser`
- `roles/firebaseauth.admin`
- `roles/logging.logWriter`

The backend now supports Application Default Credentials on Cloud Run, so you do not need to inject `FIREBASE_PRIVATE_KEY` into production if the service account has the right permissions.

## 2. Backend Environment

Start from [backend.env.yaml.example](/run/media/shrey/Data/Team%20369/Solution%20Challenge/Stocklytics-AI/infra/cloudrun/backend.env.yaml.example).

Important variables:

- `APP_ENV=production`
- `CORS_ALLOW_ORIGINS=https://YOUR_FRONTEND_HOST`
- `FIREBASE_PROJECT_ID`
- `FIRESTORE_PROJECT_ID`
- `BIGQUERY_PROJECT_ID`
- `GEMINI_API_KEY`
- `AI_PRIMARY_MODEL_ID=gemini-2.0-flash`
- `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`

## 3. Frontend Environment

Start from [frontend.env.yaml.example](/run/media/shrey/Data/Team%20369/Solution%20Challenge/Stocklytics-AI/infra/cloudrun/frontend.env.yaml.example).

Important variables:

- `NEXT_PUBLIC_USE_MOCKS=false`
- `NEXT_PUBLIC_API_BASE_URL=https://YOUR_BACKEND_HOST/api/v1`
- `BACKEND_URL=https://YOUR_BACKEND_HOST`
- Firebase Web SDK values from Firebase console

## 4. Build Images

Backend:

```bash
gcloud builds submit \
  --config infra/cloudrun/cloudbuild.backend.yaml \
  --substitutions _AR_HOSTNAME=REGION-docker.pkg.dev,_AR_REPO=stocklytics
```

Frontend:

```bash
gcloud builds submit \
  --config infra/cloudrun/cloudbuild.frontend.yaml \
  --substitutions _AR_HOSTNAME=REGION-docker.pkg.dev,_AR_REPO=stocklytics,_BACKEND_URL=https://YOUR_BACKEND_HOST,_NEXT_PUBLIC_API_BASE_URL=https://YOUR_BACKEND_HOST/api/v1,_NEXT_PUBLIC_FIREBASE_API_KEY=REPLACE,_NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=YOUR_PROJECT.firebaseapp.com,_NEXT_PUBLIC_FIREBASE_PROJECT_ID=YOUR_PROJECT,_NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=YOUR_PROJECT.firebasestorage.app,_NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=REPLACE,_NEXT_PUBLIC_FIREBASE_APP_ID=REPLACE,_APP_URL=https://YOUR_FRONTEND_HOST
```

## 5. Deploy Services

Backend:

```bash
gcloud run deploy stocklytics-backend \
  --image REGION-docker.pkg.dev/PROJECT_ID/stocklytics/stocklytics-backend:IMAGE_TAG \
  --region REGION \
  --platform managed \
  --service-account stocklytics-backend@PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --env-vars-file infra/cloudrun/backend.env.yaml
```

Frontend:

```bash
gcloud run deploy stocklytics-frontend \
  --image REGION-docker.pkg.dev/PROJECT_ID/stocklytics/stocklytics-frontend:IMAGE_TAG \
  --region REGION \
  --platform managed \
  --allow-unauthenticated
```

## 6. Production Readiness Checklist

- Create required Firestore composite indexes before launch.
- Rotate exposed API keys and move secrets to Secret Manager.
- Set Cloud Run min instances for backend if cold starts hurt UX.
- Add request throttling / retry for Gemini `429` responses.
- Run end-to-end tests against production-like env vars before go-live.
