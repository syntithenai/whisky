#!/usr/bin/env bash
set -euo pipefail

# Deploys split hosting targets:
# 1) Public static site -> GitHub Pages branch
# 2) Staff app (frontend+API) -> Google Cloud Run
# 3) Cloud SQL migrations for staff schema

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GCP_PROJECT="${GCP_PROJECT:-}"
GCP_REGION="${GCP_REGION:-australia-southeast1}"
ARTIFACT_REPO="${ARTIFACT_REPO:-whisky}"
CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-whisky-staff}"
CLOUD_SQL_INSTANCE="${CLOUD_SQL_INSTANCE:-}"
STAFF_APP_ORIGIN="${STAFF_APP_ORIGIN:-}"
GITHUB_PAGES_BRANCH="${GITHUB_PAGES_BRANCH:-gh-pages}"
IMAGE_NAME="${IMAGE_NAME:-staff-app}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$ROOT_DIR" rev-parse --short HEAD)}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_var() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
}

require_cmd git
require_cmd python3
require_cmd gcloud
require_cmd docker

require_var GCP_PROJECT "$GCP_PROJECT"
require_var CLOUD_SQL_INSTANCE "$CLOUD_SQL_INSTANCE"
require_var STAFF_APP_ORIGIN "$STAFF_APP_ORIGIN"

FULL_IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${ARTIFACT_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "==> Step 1/6: Build public static site"
python3 "$ROOT_DIR/scripts/build_github_pages.py"

if [[ ! -d "$ROOT_DIR/build/github-pages" ]]; then
  echo "Expected build/github-pages to exist after build." >&2
  exit 1
fi

echo "==> Step 2/6: Publish static artifacts to ${GITHUB_PAGES_BRANCH}"
TMP_PAGES_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_PAGES_DIR"
}
trap cleanup EXIT

git clone --quiet "$ROOT_DIR" "$TMP_PAGES_DIR/repo"
pushd "$TMP_PAGES_DIR/repo" >/dev/null

if git show-ref --verify --quiet "refs/heads/${GITHUB_PAGES_BRANCH}"; then
  git checkout "$GITHUB_PAGES_BRANCH"
else
  git checkout --orphan "$GITHUB_PAGES_BRANCH"
  git rm -rf . >/dev/null 2>&1 || true
fi

find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$ROOT_DIR/build/github-pages/." .

git add -A
if ! git diff --cached --quiet; then
  git commit -m "Deploy static site $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push origin "$GITHUB_PAGES_BRANCH"
else
  echo "No static site changes to publish."
fi

popd >/dev/null

echo "==> Step 3/6: Build and push staff image"
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

# Dockerfile expected in repository root for staff runtime.
docker build -t "$FULL_IMAGE" "$ROOT_DIR"
docker push "$FULL_IMAGE"

echo "==> Step 4/6: Deploy Cloud Run staff service"
gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --image "$FULL_IMAGE" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "STAFF_APP_ORIGIN=${STAFF_APP_ORIGIN}" \
  --add-cloudsql-instances "$CLOUD_SQL_INSTANCE"

echo "==> Step 5/6: Run staff migrations"
# Assumes image has scripts/migrate_staff_db.py and entrypoint can execute python3.
# Uses Cloud Run jobs for one-off migration execution.
MIGRATION_JOB="${CLOUD_RUN_SERVICE}-migrate"

gcloud run jobs deploy "$MIGRATION_JOB" \
  --project "$GCP_PROJECT" \
  --region "$GCP_REGION" \
  --image "$FULL_IMAGE" \
  --command python3 \
  --args scripts/migrate_staff_db.py \
  --add-cloudsql-instances "$CLOUD_SQL_INSTANCE" \
  --set-env-vars "STAFF_APP_ORIGIN=${STAFF_APP_ORIGIN}" \
  --execute-now

echo "==> Step 6/6: Summary"
STAFF_URL="$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$GCP_PROJECT" --region "$GCP_REGION" --format='value(status.url)')"

echo "Public static site branch: ${GITHUB_PAGES_BRANCH}"
echo "Staff service URL: ${STAFF_URL}"
echo "Expected public->staff redirect origin: ${STAFF_APP_ORIGIN}"
echo "Deployed image: ${FULL_IMAGE}"
