# Architecture

React/Vite presents a responsive workspace. TanStack Query calls the versioned FastAPI API; the selected demo user ID is sent in a header. FastAPI resolves the active user in SQLAlchemy and applies visibility and mutation rules. PostgreSQL stores departments, users, requests and immutable-by-convention request events; Alembic manages schema changes. SQLite is used only for isolated tests.

Requests start Submitted. The transition table lives in the API: Submitted can become Needs Information, Triaged or Cancelled; Needs Information can become Submitted, Triaged or Cancelled; Triaged can become Needs Information, In Progress or Cancelled; In Progress can become Needs Information, Resolved or Cancelled; Resolved can become In Progress or Closed. Closed and Cancelled are terminal. Purchase requests cannot enter fulfillment, resolve or close without a fully authorized approval cycle. Reopening a resolved request clears its resolution timestamp. Mutations and requester clarifications are recorded as events.

Employees see their own requests; assigned approvers can also see requests assigned to them; assigned agents see assigned work and their own requests; managers see their department's assigned work and their own requests; operations admins see all. Managers and assigned agents can manage visible assigned work; only admins can move work between departments. Requesters may add clarifications. New eligible requests are routed to a department; assigning a person is still a human action. The demo header is impersonation, not authentication.

AI interpretations, policy decisions, approvals, SLA revisions and escalations are separate request-linked entities. Cross-department plans, tasks, dependencies and handoffs are implemented as a separate request-linked workflow.

## AI request intelligence

An optional user-initiated OpenAI Responses call produces a structured, advisory analysis. Owned drafts can be linked only after the requester reviews them; the server verifies ownership and a description hash and records the review with the request transaction. Request access controls govern history. The model never assigns, approves, changes status or resolves a request. See [AI intelligence](ai-intelligence.md) for schema, evaluation and limitations.

## Phase 3 policy and workflows

Deterministic, versioned policy rules route new requests, calculate initial-response targets, and generate sequential financial approvals. PostgreSQL request-row locks serialize approval decisions and revisions. A separate local worker evaluates escalations independent of browser activity. See [policy engine](policy-engine.md), [approvals](approval-workflows.md), and [incident SLA](incident-sla.md).

## Phase 4 project orchestration

Versioned plans are reviewed before activation creates execution tasks. Parent-request row locks serialize task transitions and handoffs. The project owner explicitly completes the project, and generic request transitions cannot bypass active workflow controls. Scoped task-only access does not grant parent request visibility. AI proposes drafts only; deterministic validation enforces the dependency graph. See [workflow orchestration](workflow-orchestration.md).
# Analytics preview

The analytics service applies request visibility before aggregating request cohorts, policy decisions, approvals, incident SLAs and project tasks. Synthetic AI evaluation results are stored in separate additive tables and are not included in operational KPIs. The evaluation action is restricted to Operations Admin and is explicitly billable; simulated demo identity is not production authentication. Reporting definitions and known omissions are in [analytics-methodology.md](analytics-methodology.md) and [ai-evaluation.md](ai-evaluation.md).

