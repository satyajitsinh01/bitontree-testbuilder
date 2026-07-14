# TestBuilder Constitution

<!-- Governing principles for the TestBuilder online assessment platform.
     Every spec, plan, and task must pass the Constitution Check against this file. -->

## Core Principles

### I. Server-Authoritative Everything
All time, scoring, session, and access decisions are made on the server.
- Server IST (Asia/Kolkata) time is the single source of truth for assessment windows, section timers, and credential expiry. Client-local time is display-only.
- Timers rendered in the browser are cosmetic; expiry is enforced server-side and reconciled over WebSocket.
- No score, answer state, or proctoring verdict may be computed exclusively on the client.

### II. Immutable Audit Trail (NON-NEGOTIABLE)
- Every sensitive action (test edits, timing changes, invitation sends/resends, manual score changes, session resets, question publish/unpublish) writes an append-only audit record.
- Audit records are never updated or deleted by application code. No `UPDATE`/`DELETE` grants on the `audit_logs` table for the application DB role.
- Each record captures: actor, action, entity type + id, before/after snapshot (JSONB), timestamp (server IST), request id, and IP.

### III. Versioned Assessments
- The moment the first candidate starts an assessment, that assessment version is frozen.
- Any subsequent edit creates a new version. In-flight candidates finish on the version they started.
- Every answer, code submission, and report references the exact assessment version and question version it was produced against.
- For a question, the latest saved state at the relevant checkpoint (next-question navigation, run code, submit code) is the answer of record; the final submission uses the latest version.

### IV. Security First
- Argon2id for password hashing; short-lived JWT access tokens (≤ 15 min) + securely stored, rotated refresh tokens.
- Candidate credentials are per-assignment, temporary, and expire at the candidate's assessment end time.
- One active session per candidate assignment, enforced with a Redis lock + DB session record.
- Code execution is sandboxed (Docker, no network, CPU/memory/time limits). Untrusted code never runs on application hosts.
- All uploads (CSV, screenshots, evidence) go to object storage via pre-signed URLs; nothing user-supplied is stored on app servers.
- Secrets live in the environment/secret manager, never in the repo.

### V. AI Is a Draft Author, Never a Publisher
- AI-generated questions are created with status `draft` and require explicit human approval before they can appear in any assessment.
- AI-assisted text-answer scores and proctoring analyses are recommendations; a human evaluator can override, and overrides are audit-logged.
- Every AI output stores its prompt, model, and generation metadata for reproducibility.

### VI. Test-First, Contract-First
- API contracts (OpenAPI via FastAPI/Pydantic) are written before implementation.
- Backend: pytest with contract tests per endpoint, integration tests per user story. Frontend: Jest + React Testing Library.
- Red-Green-Refactor: tests are written and observed failing before implementation of each task marked test-first.

### VII. Simplicity & YAGNI
- Two deployable applications only: `frontend` (Next.js) and `backend` (FastAPI) plus workers. No microservice split without a documented scaling need.
- No premature abstraction: three similar lines beat a framework.
- Features not in the spec (e.g., global standalone student module) are explicitly out of scope.

## Mandated Tooling (org standard — overrides personal preference)

| Concern            | Tool                          | Forbidden                          |
| ------------------ | ----------------------------- | ---------------------------------- |
| Node packages      | npm                           | pnpm, yarn, bun                    |
| Python env/deps    | uv                            | poetry, pipenv, conda              |
| JS/TS tests        | Jest                          | Vitest, Mocha, AVA                 |
| Python tests       | pytest                        | —                                  |
| Migrations         | Alembic                       | raw SQL files outside Alembic      |
| Lint (TS)          | ESLint + Prettier             | —                                  |
| Lint (Py)          | Ruff (lint + format)          | black+flake8 combo                 |

Languages: TypeScript (frontend) and Python (backend) only. New languages require architecture review.

## Additional Constraints

- Conventional Commits required; no AI co-authorship trailers.
- All changes land via PR + review + green CI; no direct pushes to protected branches.
- No `console.log`/`print` debugging in committed code; use structured loggers (pino on FE server side is out of scope — browser logging via a thin wrapper; `structlog` on BE).
- Files > ~300 lines are a smell; split by responsibility.
- Percentile/rank appears on reports only when cohort size ≥ 20 completed candidates.

## Development Workflow

1. `spec.md` (what/why) → 2. `plan.md` (how) → 3. `tasks.md` (ordered, testable tasks) → 4. implement task-by-task with tests → 5. PR referencing task IDs.

Every PR description lists the FR-/task-IDs it satisfies. CI runs lint, type-check, Jest, pytest, and Alembic migration check.

## Governance

- This constitution supersedes ad-hoc practices. Amendments require a PR to this file with rationale and migration notes.
- The Constitution Check section of every `plan.md` must document any deviation and its justification in the Complexity Tracking table.

**Version**: 1.0.0 | **Ratified**: 2026-07-14 | **Last Amended**: 2026-07-14
