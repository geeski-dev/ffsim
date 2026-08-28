# Deployment Runbook

1. `git ls-files | grep my_leagues`

   This must return empty. `my_leagues.py` contains private league assessments and must never be committed or deployed.

2. Confirm the production API build context stays small and private data stays out:

   `docker build -t ffsim-api .`

3. Create or update the Fly app configuration:

   `fly launch --no-deploy`

   Reuse the checked-in `fly.toml`. The app runs the FastAPI service only.

4. Set any required Fly secrets, then deploy:

   `fly deploy`

5. Verify the API health check:

   `curl https://<fly-app>.fly.dev/health`

6. Configure Cloudflare Pages with the production API URL:

   `VITE_API_URL=https://<fly-app>.fly.dev`

   Keep this as a Cloudflare Pages environment variable. Do not point the production frontend at localhost.

7. Deploy the frontend from Cloudflare Pages after the API health check passes.
