# Stock Picker

Phase 1 is a single-user paper-trading research system. It scans a liquid US equity universe, creates deterministic mid-term and long-term research signals, records source-backed evidence, sends Discord-ready notification records, and tracks mock portfolio performance against SPY, QQQ, and VTI.

## Security First

Do not create real `.env` files from Codex. Use `env.example` as the placeholder template and export real values from your shell or a secrets manager.

Before changing configuration, auth, providers, notifications, or deployment, run:

```bash
make security-scan
```

## Local Development

Backend:

```bash
cd backend
uv pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Docker Compose:

```bash
export ADMIN_PASSWORD="<local-only>"
export SESSION_SECRET_KEY="<local-only>"
export CSRF_SECRET_KEY="<local-only>"
docker compose up --build
```

The app is available at `http://localhost:5173`, with the API at `http://localhost:8000`.

`ALLOW_DEMO_DATA=true` seeds local demo snapshots so the UI and scoring workflow can be tested without provider keys. Set `APP_ENV=production` and `ALLOW_DEMO_DATA=false` for production; production startup rejects demo data and placeholder secrets.

## Verification

```bash
make backend-test
make backend-lint
make frontend-build
make security-scan
PRE_COMMIT_HOME=.cache/pre-commit pre-commit run --all-files
```
