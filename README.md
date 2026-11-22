# OpsPilot

OpsPilot is a portfolio prototype for Meridian Group, a fictional professional services organization. It provides persistent service requests, scoped demo roles, assignment, validated lifecycle transitions, an audit trail, and database-derived dashboards. Optional AI request analysis supports human review; deterministic routing, purchase approvals and incident response targets are implemented as fictional demo workflows. Cross-department projects support reviewed plans, task dependencies and audited handoffs.

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

To run the PostgreSQL integration test, point `TEST_POSTGRES_URL` at a disposable database whose user can create schemas. The test creates and removes its own randomly named schema; it does not use the application's tables. For example, in PowerShell from `backend`:

```powershell
$env:TEST_POSTGRES_URL = 'postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot'
.\.venv\Scripts\python.exe -m pytest -q tests/test_postgres_integration.py
Remove-Item Env:TEST_POSTGRES_URL
```

## Prototype and security limitations

The demo-user selector and `X-Demo-User-Id` header simulate identity. Anyone able to call the API can select any seeded identity; this is not authentication, and the application must not be exposed to untrusted users or deployed as a production service. Authorization rules are enforced against the selected database user but do not establish identity. Data is fictional. No external purchasing or payment, SSO, rate limiting, CSRF controls, or production hardening is implemented. Demo reset deletes records and is intended only for a disposable local database.




## Optional AI request intelligence

Copy `backend/.env.example` to `backend/.env` and set `OPENAI_API_KEY` there (never commit it). The backend reads `OPENAI_MODEL` (default `gpt-6-luna`), `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_OUTPUT_TOKENS`, and `OPENAI_MAX_INPUT_CHARS`. Restart the backend after changing environment variables and run `alembic upgrade head`. With no key, the Analyze action explains that AI is unavailable and manual request creation still works.

Selecting Analyze explicitly sends the entered draft title, type, and description to OpenAI. Avoid sensitive data in a demo. Analysis is advisory and must be reviewed: choose suggestions selectively, edit the final request, and submit. Department suggestions do not assign work. If the description changes, reanalyze to attach a current result; otherwise manual submission remains available. Successful linked analyses and review choices are visible to users who can view the request.

The OpenAI Responses API uses schema-constrained Pydantic output. It does not guarantee truth or prevent prompt injection. Missing credentials, provider errors, refusals, incomplete output and timeouts do not generate substitute recommendations. Critical and suspected security issues receive deterministic review flags; all recommendations require human review. The system does not approve purchases, change status or assign work.

Analyses store extracted text and a hash of the input description (not the raw draft or API key), model identity, token counts and review choices. Abandoned draft analyses currently have no automatic expiry. The demo identity switcher is not authentication, so do not expose this prototype publicly or use real sensitive information. See [AI architecture and evaluation](docs/ai-intelligence.md).

Live evaluation is opt-in and incurs API charges. From `backend`, after configuring a key:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run --live --limit 30
```

## Phase 3 policy workflows

After migrations, run `python -m app.seed` from `backend` to add fictional approvers and separately named workflow examples without modifying existing requests. Start an independent local escalation worker in another PowerShell terminal:

```powershell
cd C:\Users\chase\Documents\GitHub\OpsPilot\backend
.\.venv\Scripts\python.exe -m app.escalation_worker --watch --interval 60
```

The worker must remain running for periodic checks. Run it without `--watch` for one evaluation. Purchases require confirmed USD total commitment and sequential approvals; generic status changes cannot bypass financial authorization. Critical and overdue incidents produce in-app escalations, not external notifications. For rules, role limits, examples and holidays see [policy engine](docs/policy-engine.md), [purchase approvals](docs/approval-workflows.md) and [incident SLAs](docs/incident-sla.md).

## Phase 4 project workflows

After applying migrations and rerunning the idempotent demo seed, open Workflows or a cross-department request. Create a workflow, save and submit a manual plan, then explicitly approve activation. Task dependencies control when work becomes ready; a project owner must explicitly authorize final completion. AI planning is optional and creates only a draft. Assigned users without request visibility can use My Tasks without gaining access to the full request.

See [workflow orchestration](docs/workflow-orchestration.md) for the marketing campaign demonstration, permissions and optional billable AI planning check.
# Phase 5 analytics preview

Select a Department Manager or Operations Admin to open Analytics. Reporting is scoped to a fixed department or organization cohort; Operations Admin can also explicitly run the billable synthetic AI evaluation. Enter the model's current token prices and a budget before starting. The budget is a planning estimate, not a provider-enforced spending limit. The 100-case synthetic dataset is exploratory and all labels await human review. No live evaluation runs automatically.

Business Impact accepts illustrative assumptions and exports a JSON scenario. It does not claim observed labor savings. The Analytics workspace reads an isolated fictional dataset; the existing general analytics endpoint retains its coarse restrictions. See [analytics methodology](docs/analytics-methodology.md), [AI evaluation](docs/ai-evaluation.md), [process comparison](docs/process-comparison.md), and [ROI model](docs/roi-model.md).

### Set up the isolated synthetic analytics dataset

Use a **new empty local database**. The initialization command refuses to label a nonempty unmarked database as synthetic. Do not put real data in this database or point the application API at it for normal use. These commands preserve the ordinary `opspilot` database:

```powershell
docker compose up -d
docker compose exec -T db createdb -U opspilot opspilot_synthetic
cd backend
$env:DATABASE_URL = 'postgresql+psycopg://opspilot:opspilot@127.0.0.1:5432/opspilot_synthetic'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.synthetic_seed
Remove-Item Env:DATABASE_URL
```

The `createdb` step is needed only once. Add `SYNTHETIC_DATABASE_URL=postgresql+psycopg://opspilot:opspilot@127.0.0.1:5432/opspilot_synthetic` to `backend/.env` and restart the backend. The dataset initialization is idempotent and does not backfill or modify the ordinary database. Analytics reads it in a read-only database transaction. This is a portfolio simulation, not a secure isolation boundary against a database administrator or an incorrectly configured external writer.

