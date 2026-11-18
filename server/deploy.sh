#!/usr/bin/env bash
# Deploy the LeetRecall AI backend to Cloud Run (built remotely by Cloud Build; no local Docker needed).
#
# One-time, run by YOU (these touch credentials):
#   grep '^ANTHROPIC_API_KEY=' server/.env | cut -d= -f2- | tr -d '\n' | gcloud secrets create anthropic-api-key --data-file=-
#   openssl rand -hex 24 | tr -d '\n' | gcloud secrets create leetrecall-api-key --data-file=-
# Optional, for persistent storage (otherwise each instance seeds an in-container Qdrant on start):
#   printf '%s' "<qdrant-cloud-url>"     | gcloud secrets create qdrant-url --data-file=-
#   printf '%s' "<qdrant-cloud-api-key>" | gcloud secrets create qdrant-api-key --data-file=-
#
# Then:  bash server/deploy.sh
set -euo pipefail

PROJECT="${PROJECT:-leetrecall-20040119}"
REGION="${REGION:-us-east1}"
SERVICE="${SERVICE:-leetrecall-ai}"
SA="leetrecall-run@${PROJECT}.iam.gserviceaccount.com"
cd "$(dirname "$0")"

secrets=(anthropic-api-key leetrecall-api-key)
env_secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,LEETRECALL_API_KEY=leetrecall-api-key:latest"
if gcloud secrets describe qdrant-url --project "$PROJECT" >/dev/null 2>&1; then
  secrets+=(qdrant-url qdrant-api-key)
  env_secrets+=",QDRANT_URL=qdrant-url:latest,QDRANT_API_KEY=qdrant-api-key:latest"
  echo "storage: Qdrant Cloud"
else
  echo "storage: in-container Qdrant seeded from data/ (ephemeral; set qdrant-url/qdrant-api-key secrets to persist)"
fi

# least privilege: the runtime service account can read exactly these secrets, nothing else
for s in "${secrets[@]}"; do
  gcloud secrets describe "$s" --project "$PROJECT" >/dev/null || { echo "missing secret: $s (see header)"; exit 1; }
  gcloud secrets add-iam-policy-binding "$s" --project "$PROJECT" \
    --member "serviceAccount:${SA}" --role roles/secretmanager.secretAccessor >/dev/null
done

# --allow-unauthenticated: the extension can't mint Google IAM tokens; X-API-Key is the gate.
# max-instances x LEETRECALL_MAX_CONCURRENT_DRAFTS bounds spend if the key ever leaks.
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source . \
  --service-account "$SA" \
  --set-secrets "$env_secrets" \
  --set-env-vars "LEETRECALL_OTEL_EXPORTER=gcp,LEETRECALL_MAX_CONCURRENT_DRAFTS=2" \
  --memory 2Gi --cpu 2 --timeout 300 --concurrency 8 \
  --min-instances 0 --max-instances 2 \
  --allow-unauthenticated

URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')
echo "deployed: $URL"
curl -fsS "$URL/healthz" && echo
