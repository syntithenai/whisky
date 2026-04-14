# Deployment Setup Guide

Before running `scripts/deploy_split_hosting.sh` you need to complete three short steps manually: authenticate the CLI, create an OAuth client, and fill in a `.env` file. The script handles everything else (enabling APIs, creating cloud resources, running migrations).

---

## Prerequisites

You need `git`, `python3`, `docker`, and the Google Cloud CLI installed.

```bash
# Install Google Cloud CLI (Debian/Ubuntu)
sudo apt-get install google-cloud-cli

# Install Docker (Debian/Ubuntu)
sudo apt-get install docker.io
sudo usermod -aG docker "$USER"   # then log out and back in
```

---

## Step 1 — Authenticate the Google Cloud CLI

```bash
# Log in your personal Google account
gcloud auth login

# Create application-default credentials (used by Docker and the Python SDK)
gcloud auth application-default login
```

Both commands open a browser tab. Sign in with the Google account that has Owner or Editor access to the GCP project.

Confirm it worked:

```bash
gcloud auth list
# Your account should appear with an asterisk *
```

---

## Step 2 — Create an OAuth Client ID for Google Sign-In

The staff app uses Google Sign-In. You must create credentials in the Google Cloud Console — this can't be scripted.

**2a. Configure the OAuth consent screen**

1. Open https://console.cloud.google.com/apis/credentials/consent
2. Select **Internal** if your staff all use the same Google Workspace domain (recommended — restricts login to that domain automatically), or **External** to manage allowed emails individually.
3. Fill in App name (e.g. `Whisky Staff`), support email, and developer contact email.
4. No extra scopes needed — the defaults (`openid`, `email`, `profile`) are sufficient.
5. Save.

**2b. Create a client ID**

1. Open https://console.cloud.google.com/apis/credentials
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: `whisky-staff-web`
5. Under **Authorised JavaScript origins** (not redirect URIs) add:
   - `https://YOUR_CLOUD_RUN_URL` *(add this after first deploy once you know the URL)*
   - `http://localhost:8081` *(for local development — Google whitelists localhost automatically)*
6. Leave **Authorised redirect URIs** empty.
7. Click **Create**

You will see a dialog with your **Client ID**. Copy it — you need it for the `.env` file in step 3. There is no client secret to copy; GIS does not use one.

---

## Step 3 — Create the .env File

Create a `.env` file in the project root. Fill in the three required values; everything else has a working default.

```bash
cat > .env <<'EOF'
# ── Required ────────────────────────────────────────────────────────────────

# Your GCP project ID (visible at console.cloud.google.com)
GCP_PROJECT=your-project-id

# From Step 2b above — client ID only, no secret needed
OIDC_CLIENT_ID=123456789-xxxx.apps.googleusercontent.com

# ── Optional — change only if you need non-default names ────────────────────

# GCP region; australia-southeast1 (Sydney) is the default
# GCP_REGION=australia-southeast1

# Cloud Run service name
# CLOUD_RUN_SERVICE=whisky-staff

# Git branch the static site is published to
# GITHUB_PAGES_BRANCH=gh-pages
EOF
```

Add `.env` to `.gitignore` so it is never committed:

```bash
grep -qxF '.env' .gitignore || echo '.env' >> .gitignore
```

---

## Step 4 — Run the Script

```bash
set -a && source .env && set +a
./scripts/deploy_split_hosting.sh
```

The script will:

1. Build the static public site and push it to the `gh-pages` branch
2. Enable the required GCP APIs if they are not already enabled
3. Create the Artifact Registry repository if it does not exist
4. Build and push the staff container image
5. Create the Cloud SQL instance and database if they do not exist
6. Store DB credentials in Secret Manager
7. Deploy the Cloud Run service
8. Run database migrations
9. Print the public site URL and staff service URL

**First deploy takes 5–10 minutes** while Cloud SQL provisions. Subsequent deploys are faster.

---

## Step 5 — Register the Cloud Run JavaScript Origin

After the first deploy, the script prints the Cloud Run URL, e.g.:

```
Staff service URL: https://whisky-staff-abc123-ts.a.run.app
```

Go back to https://console.cloud.google.com/apis/credentials, edit your OAuth client, and add the Cloud Run URL as an **Authorised JavaScript origin** (not a redirect URI):

```
https://whisky-staff-abc123-ts.a.run.app
```

This is a one-time step. The URL is stable for the lifetime of the Cloud Run service.

---

## Enabling GitHub Pages

The `gh-pages` branch is created automatically by the script. You must enable Pages in the repository settings once:

1. Go to your GitHub repository → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `gh-pages` / `/ (root)`
4. Save

The public site will then be live at `https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/`.

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT` | yes | — | GCP project ID |
| `OIDC_CLIENT_ID` | yes | — | OAuth 2.0 client ID from Google Console (no secret needed) |
| `GCP_REGION` | no | `australia-southeast1` | GCP region |
| `ARTIFACT_REPO` | no | `whisky` | Artifact Registry repository name |
| `CLOUD_RUN_SERVICE` | no | `whisky-staff` | Cloud Run service name |
| `CLOUD_SQL_INSTANCE_NAME` | no | `whisky-db` | Cloud SQL instance name |
| `GITHUB_PAGES_BRANCH` | no | `gh-pages` | Branch for static site |
| `IMAGE_NAME` | no | `staff-app` | Docker image name |
| `IMAGE_TAG` | no | current git SHA | Docker image tag |
