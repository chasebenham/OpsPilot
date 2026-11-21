# Architecture

React/Vite presents a responsive workspace. TanStack Query calls the versioned FastAPI API; the selected demo user ID is sent in a header. FastAPI resolves the active user in SQLAlchemy and applies visibility and mutation rules. PostgreSQL stores departments, users, requests and immutable-by-convention request events; Alembic manages schema changes. SQLite is used only for isolated tests.

Requests start Submitted. The transition table lives in the API: Submitted can become Needs Information, Triaged or Cancelled; Needs Information can become Submitted, Triaged or Cancelled; Triaged can become Needs Information, In Progress or Cancelled; In Progress can become Needs Information, Resolved or Cancelled; Resolved can become In Progress or Closed. Closed and Cancelled are terminal. Purchase requests cannot resolve or close without a future approval module. Reopening a resolved request clears its resolution timestamp. Mutations and requester clarifications are recorded as events.

Employees and finance approvers see their own requests; assigned agents see assigned work and their own requests; managers see their department's assigned work and their own requests; operations admins see all. Managers and assigned agents can manage visible assigned work; only admins can move work between departments. Requesters may add clarifications. Newly submitted unassigned work requires an operations admin to assign it. The demo header is impersonation, not authentication.

Future AI interpretations, policies, approvals and workflow tasks should be separate entities linked to requests, with explicit authorization and versioned policy decisions. No future functionality is simulated as completed.

## AI request intelligence

An optional user-initiated OpenAI Responses call produces a structured, advisory analysis. Owned drafts can be linked only after the requester reviews them; the server verifies ownership and a description hash and records the review with the request transaction. Request access controls govern history. The model never assigns, approves, changes status or resolves a request. See [AI intelligence](ai-intelligence.md) for schema, evaluation and limitations.
