# OpsPilot

OpsPilot is a Phase 1 portfolio prototype for Meridian Group, a fictional professional services organization. It provides persistent service requests, scoped demo roles, assignment, validated lifecycle transitions, an audit trail, and database-derived dashboards. AI analysis, purchasing approvals and workflow automation are future work.

## Prerequisites

Python 3.11+ with pip, Node.js 20.19+ or 22.12+, and Docker Desktop with Compose and its daemon running. PostgreSQL 16 can instead be supplied locally.

## Local setup

From the repository root:

```bash
docker compose up -d
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Copy .env.example to .env and adjust DATABASE_URL if needed
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and select a demo user. API documentation is at http://localhost:8000/docs. Vite proxies `/api` to port 8000. Seed is idempotent when the database is already populated. To **delete all demo records** and restore a fresh local seed, run `python -m app.seed --reset` from `backend`; reset is restricted to a local PostgreSQL database named `opspilot`. Do not point it at a database containing valuable data. Migrations are applied separately with `alembic upgrade head`.

## Tests and build

```bash
cd backend
pytest -q
cd ../frontend
npm run build
npm test
```

Tests use an isolated in-memory SQLite database; they do not replace PostgreSQL integration testing.

## Prototype and security limitations

The demo-user selector and `X-Demo-User-Id` header simulate identity. Anyone able to call the API can select any seeded identity; this is not authentication, and the application must not be exposed to untrusted users or deployed as a production service. Authorization rules are enforced against the selected database user but do not establish identity. Data is fictional. No AI, purchase approval, multi-step workflow, SSO, rate limiting, CSRF controls, or production hardening is implemented. Purchase completion is blocked pending the approval phase. Demo reset deletes records and is intended only for a disposable local database.


