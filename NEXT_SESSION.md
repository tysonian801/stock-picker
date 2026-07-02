# Next Session Handoff

Continue work in `/Users/tysonian/repos/stock-picker`.

## Start Here
- Inspect `git status` and `AGENTS.md`.
- Do not read `.env`, `.env.*`, key files, credential files, or secret-like paths.
- Do not commit or push unless explicitly asked.

## Confirmed Working
- Backend FastAPI app is implemented.
- React/Vite frontend is implemented.
- Docker Compose starts the app stack and the login page is reachable at `http://localhost:5173`.
- Login works with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from the local environment.
- Running a scan populates recommendations.
- Recommendation prices are displayed.
- Repeated scans no longer duplicate historical recommendations in the main list; the list shows the latest completed scan.
- Mock buy flow works and adds trades to trade history.
- Buy form ticker changes update the estimated price.
- Mock trade price defaults to the backend's latest available price instead of requiring manual price input.
- Portfolio updates after mock buys.
- Security scans and hooks are in place.

## Confirmed Verification
These checks passed:

```bash
UV_CACHE_DIR=.cache/uv uv run --project backend pytest
UV_CACHE_DIR=.cache/uv uv run --project backend ruff check .
cd frontend && npm run build
cd frontend && npm audit
make security-scan
PRE_COMMIT_HOME=.cache/pre-commit pre-commit run --all-files
```

Security fixes completed:
- Provider HTTP failures are sanitized so API keys are not exposed through exception text.
- Discord webhook failures are sanitized so webhook URLs/tokens are not exposed.
- Failed Discord dispatch marks notifications as `failed` instead of bubbling raw HTTP errors.
- Logout revokes the server-side session token.
- Basic login throttling is implemented.
- Accidental root-level npm manifest files were removed; only `frontend/package.json` and `frontend/package-lock.json` should be tracked.

## Needs Testing Next
Run Docker Compose after the latest changes:

```bash
export ADMIN_PASSWORD="<local-only>"
export SESSION_SECRET_KEY="<local-only>"
export CSRF_SECRET_KEY="<local-only>"
docker compose up --build
```

Then test in the browser:
- Login.
- Run scan.
- Confirm recommendations load without historical duplicates.
- Confirm recommendation evidence is visible.
- Buy one whole share from a recommendation.
- Change ticker in the trade form and confirm estimated price changes.
- Confirm trade history and portfolio update after buy.
- Confirm stock performance chart shows trade markers.
- Try logout, then confirm the prior session is no longer usable after refresh.
- Trigger several failed logins and confirm throttling occurs.

## Not Fully Developed Yet
- Editing or deleting existing mock trades is not implemented. Current workaround is offsetting trades.
- Live market prices are not guaranteed unless provider API keys are configured and refresh succeeds. Demo seeded prices are still used when `ALLOW_DEMO_DATA=true`.
- UI needs a design and usability pass; current focus has been functional validation.
- Recommendation rows still show separate mid-term and long-term horizons for the same ticker by design, but grouping/filtering by ticker/horizon is not implemented.
- Data source and timestamp are not yet shown beside recommendation prices; this should be added before relying on prices for real decisions.
- Provider refresh behavior with real FMP, Alpha Vantage, and Finnhub keys still needs end-to-end testing.
- Discord notification delivery with a real webhook still needs end-to-end testing.
- Production deployment hardening is incomplete: Compose exposes Postgres/Redis ports and uses local-development defaults.

## Notes
- Do not use `npm audit fix --force` without reviewing the dependency changes.
- Do not create or edit real `.env` files from Codex.
- Stage specific files only when preparing a commit.
