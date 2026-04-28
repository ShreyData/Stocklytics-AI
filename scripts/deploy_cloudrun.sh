#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <PROJECT_ID> <REGION> [FRONTEND_HOST]"
  echo "Example: $0 stocklyitics-ai asia-south1"
  echo "Example with custom host: $0 stocklyitics-ai asia-south1 demo.example.com"
  exit 1
fi

PROJECT_ID="$1"
REGION="$2"
FRONTEND_HOST="${3:-}"
AR_REPO="${AR_REPO:-stocklytics}"
BACKEND_SERVICE_NAME="${BACKEND_SERVICE_NAME:-stocklytics-backend}"
FRONTEND_SERVICE_NAME="${FRONTEND_SERVICE_NAME:-stocklytics-frontend}"
BACKEND_SERVICE_ACCOUNT="${BACKEND_SERVICE_ACCOUNT:-stocklytics-backend@${PROJECT_ID}.iam.gserviceaccount.com}"
AR_HOSTNAME="${REGION}-docker.pkg.dev"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"
PLACEHOLDER_FRONTEND_URL="https://pending-frontend-host.invalid"
FRONTEND_URL="${PLACEHOLDER_FRONTEND_URL}"

if [[ -n "${FRONTEND_HOST}" ]]; then
  FRONTEND_URL="https://${FRONTEND_HOST}"
fi

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 1
  fi
}

for name in \
  NEXT_PUBLIC_FIREBASE_API_KEY \
  NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
  NEXT_PUBLIC_FIREBASE_PROJECT_ID \
  NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET \
  NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID \
  NEXT_PUBLIC_FIREBASE_APP_ID
do
  require_env "$name"
done

TMP_BACKEND_ENV="$(mktemp)"
trap 'rm -f "$TMP_BACKEND_ENV"' EXIT

awk -v cors_origin="${FRONTEND_URL}" '
  BEGIN { updated = 0 }
  /^CORS_ALLOW_ORIGINS=/ {
    print "CORS_ALLOW_ORIGINS=" cors_origin
    updated = 1
    next
  }
  { print }
  END {
    if (!updated) {
      print "CORS_ALLOW_ORIGINS=" cors_origin
    }
  }
' infra/cloudrun/backend.env.yaml > "${TMP_BACKEND_ENV}"

echo "Using project: ${PROJECT_ID}"
echo "Using region: ${REGION}"
echo "Frontend URL: ${FRONTEND_URL}"

gcloud config set project "${PROJECT_ID}"

gcloud builds submit \
  --config infra/cloudrun/cloudbuild.backend.yaml \
  --substitutions "_AR_HOSTNAME=${AR_HOSTNAME},_AR_REPO=${AR_REPO},_IMAGE_TAG=${IMAGE_TAG}"

gcloud run deploy "${BACKEND_SERVICE_NAME}" \
  --image "${AR_HOSTNAME}/${PROJECT_ID}/${AR_REPO}/${BACKEND_SERVICE_NAME}:${IMAGE_TAG}" \
  --region "${REGION}" \
  --platform managed \
  --service-account "${BACKEND_SERVICE_ACCOUNT}" \
  --allow-unauthenticated \
  --env-vars-file "${TMP_BACKEND_ENV}"

BACKEND_SERVICE_URL="$(gcloud run services describe "${BACKEND_SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')"
BACKEND_HOST_FROM_DEPLOY="${BACKEND_SERVICE_URL#https://}"

gcloud builds submit \
  --config infra/cloudrun/cloudbuild.frontend.yaml \
  --substitutions "_AR_HOSTNAME=${AR_HOSTNAME},_AR_REPO=${AR_REPO},_IMAGE_TAG=${IMAGE_TAG},_BACKEND_URL=${BACKEND_SERVICE_URL},_NEXT_PUBLIC_API_BASE_URL=${BACKEND_SERVICE_URL}/api/v1,_NEXT_PUBLIC_FIREBASE_API_KEY=${NEXT_PUBLIC_FIREBASE_API_KEY},_NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=${NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN},_NEXT_PUBLIC_FIREBASE_PROJECT_ID=${NEXT_PUBLIC_FIREBASE_PROJECT_ID},_NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=${NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET},_NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=${NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID},_NEXT_PUBLIC_FIREBASE_APP_ID=${NEXT_PUBLIC_FIREBASE_APP_ID},_APP_URL=${FRONTEND_URL}"

gcloud run deploy "${FRONTEND_SERVICE_NAME}" \
  --image "${AR_HOSTNAME}/${PROJECT_ID}/${AR_REPO}/${FRONTEND_SERVICE_NAME}:${IMAGE_TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated

FRONTEND_SERVICE_URL="$(gcloud run services describe "${FRONTEND_SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')"
FINAL_FRONTEND_URL="${FRONTEND_SERVICE_URL}"

if [[ -n "${FRONTEND_HOST}" ]]; then
  FINAL_FRONTEND_URL="https://${FRONTEND_HOST}"
fi

gcloud run services update "${BACKEND_SERVICE_NAME}" \
  --region "${REGION}" \
  --update-env-vars "CORS_ALLOW_ORIGINS=${FINAL_FRONTEND_URL}"

echo
echo "Deployment complete."
echo "Backend:  ${BACKEND_SERVICE_URL}"
echo "Frontend: ${FRONTEND_SERVICE_URL}"
echo
echo "Backend CORS origin set to: ${FINAL_FRONTEND_URL}"
if [[ -z "${FRONTEND_HOST}" ]]; then
  echo "If you later attach a custom frontend domain, rerun this script with that host so backend CORS is updated."
fi
echo "Backend host detected from deploy: ${BACKEND_HOST_FROM_DEPLOY}"
