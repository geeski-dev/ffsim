# Deployment Runbook

1. `git ls-files | grep my_leagues`

   This must return empty. `my_leagues.py` contains private league assessments and must never be committed or deployed.

2. Confirm the production build context stays small and private data stays out:

   `docker build -t ffsim-api .`

   The `Dockerfile` is two-stage: a Node stage runs `npm run build` to produce
   `web/dist`, and the Python stage copies that build in alongside the API.
   One image contains both halves.

3. Create or update the Fly app configuration:

   `fly launch --no-deploy`

   Reuse the checked-in `fly.toml`. The app serves the FastAPI API under
   `/api` and the built frontend at `/` from the same origin — there is no
   separate frontend deploy, and no CORS configuration to maintain.

4. Decide whether this deployment serves live simulation.

   `fly.toml` sets `FFSIM_LIVE_SIM = "0"`, which is the one setting in that
   file you have to make a decision about. With it set to `"0"`, `/api/simulate`
   returns 503 before doing any work and the frontend hides the Simulate tab
   entirely. Unset or any other value enables it, which is the default
   everywhere else — local dev, the CLI and the tests are unaffected.

   Leave it at `"0"` on any shared-CPU machine. A Monte Carlo run's wall-clock
   time there depends on the machine's remaining CPU burst budget rather than
   on the request, so no request cap can bound it; the measurements are in
   `docs/CHANGE_LEDGER.md` (CL-005). Only turn it on after moving to a
   dedicated CPU or optimising the pick loop.

5. Set any required Fly secrets, then deploy:

   `fly deploy`

6. Verify the API health check:

   `curl https://<fly-app>.fly.dev/health`

7. Verify the frontend is being served from the same app:

   `curl -I https://<fly-app>.fly.dev/`

   Expect `200` and `content-type: text/html`. If this 404s, `web/dist` was
   missing from the image — `api/main.py` skips the static mount when the
   directory isn't there, so the API still answers while the board does not.

8. Leave `VITE_API_URL` unset for this deploy. The client falls back to
   relative `/api` paths, which is what single-origin serving needs; setting
   it would point the bundled frontend at a different host. It exists for the
   case where the frontend is hosted separately from the API.
