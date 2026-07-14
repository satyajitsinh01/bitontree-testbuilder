# Implementation Plan: TestBuilder — Online Assessment Platform

**Branch**: `001-testbuilder-platform` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-testbuilder-platform/spec.md`

## Summary

Invitation-only assessment platform: admins build versioned, sectioned tests from a question bank (with AI-drafted questions gated by human approval); candidates take proctored, timed, auto-saving exams including sandboxed coding challenges; evaluation combines exact MCQ scoring, test-case code scoring, and AI-assisted written review with human override; reports aggregate scores, timelines, and proctoring evidence.

Technical approach: Next.js (TypeScript) frontend + FastAPI (Python) backend monorepo; PostgreSQL as system of record with Redis for sessions/locks/queues/cache; ARQ (async Redis-native) workers for email, AI, evaluation, and proctoring analysis — no Celery; Judge0 CE (Dockerized, no-network) for code execution; AWS S3 for evidence and files; WebSockets for timer sync and live proctoring events; Resend for email; Google Gemini API for all AI features.

## Technical Context

**Language/Version**: TypeScript 5.x / Node 20 LTS (FE); Python 3.12 (BE)
**Primary Dependencies (FE)**: Next.js 15 (App Router), Tailwind CSS, **shadcn/ui as the design system** — professional admin UI built entirely from shadcn primitives (DataTable on TanStack Table, Form, Dialog, Command palette, Charts, Sidebar layout, dark mode via next-themes; consistent tokens in `globals.css`, no ad-hoc component styling), TanStack Query v5, React Hook Form + Zod, Monaco Editor, native WebSocket client
**Primary Dependencies (BE)**: FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2, python-jose/pyjwt (JWT), argon2-cffi, ARQ (background jobs — Celery removed), redis-py, httpx (Judge0/Resend), google-genai (Gemini SDK), structlog
**Storage**: PostgreSQL 16 (+ PgBouncer, transaction pooling); Redis 7 (sessions, locks, cache, ARQ job queue, rate limits, temp exam state); AWS S3 (CSV imports, screenshots, evidence, PDF reports)
**Code Execution**: Judge0 CE self-hosted (Docker Compose), isolated containers, no internet, CPU/mem/time limits; languages: JS, Python, Java, C++, C
**AI Provider**: Google Gemini API via the official `google-genai` Python SDK, authenticated with a Gemini API key (`GEMINI_API_KEY`) — question generation, written-answer evaluation, report summaries, screenshot analysis — behind an internal `ai/` service module with provider abstraction
**Email**: Resend (transactional) via ARQ tasks with delivery webhooks
**Testing**: three levels per module — unit (pytest / Jest+RTL), functional/contract (pytest + httpx ASGI client per endpoint), feature/E2E (Playwright — approved exception, adopted). Full per-module test matrices, IDs, coverage gates, and FR traceability in [testing-strategy.md](./testing-strategy.md)
**Target Platform**: Linux containers (Docker Compose dev; any container platform prod)
**Project Type**: web (frontend + backend monorepo)
**Performance Goals**: NFR-001..004 in spec (p95 < 300 ms exam path @ 1k concurrent; autosave loss ≤ 3 s)
**Constraints**: server-IST authority, one active session per assignment, immutable audit log, frozen assessment versions
**Scale/Scope**: v1 targets 1,000 concurrent candidates, 100k questions, 10k candidates/assessment

## Constitution Check

| Principle | Status | Notes |
| --- | --- | --- |
| I. Server-authoritative time/scoring | PASS | All gating in BE using IST; WS timer sync is display-only |
| II. Immutable audit trail | PASS | Append-only `audit_logs`; DB role without UPDATE/DELETE; middleware auto-captures |
| III. Versioned assessments | PASS | `assessment_versions` snapshot; freeze-on-first-start trigger |
| IV. Security first | PASS | Argon2id, 15-min JWT + rotating refresh, per-assignment creds, sandboxed runner, pre-signed URLs |
| V. AI drafts only | PASS | `status=draft` default; approval workflow; overridable AI scores |
| VI. Test-first, contract-first | PASS | OpenAPI generated from FastAPI; contract tests precede implementation |
| VII. Simplicity | PASS | 2 apps + workers; no microservices; Judge0 reused instead of custom runner (v1) |
| Tooling mandates | PASS | npm, Jest, uv, pytest, Alembic, Ruff, ESLint |

**Initial Constitution Check: PASS** — no complexity deviations to track.

## Project Structure

### Documentation (this feature)
```
specs/001-testbuilder-platform/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: decisions & rationale
├── data-model.md        # Phase 1: entities, schema, state machines
├── quickstart.md        # Phase 1: dev environment & smoke test
├── testing-strategy.md  # Phase 1: unit/functional/feature test matrices per module (UT-/FT-/FE-*)
├── contracts/
│   ├── api-contracts.md # REST endpoints per module
│   └── ws-contracts.md  # WebSocket channels & events
└── tasks.md             # Phase 2: ordered implementation tasks
```

### Source Code (repository root)
```
backend/
├── pyproject.toml                 # uv-managed
├── alembic/                       # migrations
├── src/testbuilder/
│   ├── main.py                    # FastAPI app factory
│   ├── config.py                  # pydantic-settings
│   ├── db/                        # engine, session, base
│   ├── models/                    # SQLAlchemy models (one file per aggregate)
│   ├── schemas/                   # Pydantic request/response models
│   ├── api/
│   │   ├── deps.py                # auth, RBAC, org scoping dependencies
│   │   └── routes/                # auth, admin_users, assessments, sections,
│   │                              # questions, ai_questions, assignments,
│   │                              # candidate_auth, exam, code, proctoring,
│   │                              # evaluations, reports, emails, audit
│   ├── services/                  # business logic (one module per domain)
│   │   ├── audit.py  session.py  versioning.py  scoring.py
│   │   ├── pool_selection.py  import_candidates.py  credentials.py
│   │   └── ai/ (generation.py, written_eval.py, proctor_analysis.py, summary.py)
│   ├── workers/                   # ARQ worker settings + jobs (email, exec, ai, reports, reminders) + cron sweeps
│   ├── judge/                     # Judge0 client + result mapping
│   ├── ws/                        # WebSocket endpoints (exam channel, admin live view)
│   └── storage/                   # S3 pre-signed URL helpers (boto3)
└── tests/
    ├── contract/                  # per-endpoint schema tests
    ├── integration/               # per user story
    └── unit/                      # services

frontend/
├── package.json                   # npm-managed
├── src/
│   ├── app/
│   │   ├── (admin)/               # admin panel routes: dashboard, assessments,
│   │   │                          # questions, candidates, reports, audit, users
│   │   ├── (candidate)/           # invite login, device-check, exam, success
│   │   └── api/                   # route handlers (BFF only where needed)
│   ├── components/                # shadcn/ui-based components
│   │   ├── exam/                  # QuestionRenderer, SectionTimer, ProgressPalette,
│   │   │                          # CodeEditor (Monaco), DeviceCheck, ProctorGuard
│   │   └── admin/                 # TestBuilder, QuestionBank, CandidateTable, ReportView
│   ├── lib/                       # api client (typed from OpenAPI), ws client,
│   │                              # proctoring hooks (fullscreen, blur, copy/paste, camera)
│   ├── hooks/                     # useAutosave, useServerTimer, useExamSession
│   └── types/                     # generated API types
└── tests/                         # Jest + RTL

infra/
├── docker-compose.yml             # postgres, pgbouncer, redis, judge0, minio (dev S3)
└── docker/                        # Dockerfiles for api, worker, frontend
```

**Structure Decision**: Web application (Option 2 — frontend + backend), single repo.

## Architecture Decisions (details in research.md)

1. **Judge0 CE over custom runner (v1)** — proven isolation + language support; custom runner deferred until scale demands.
2. **Exam state**: PostgreSQL is the system of record for answers/checkpoints; Redis holds the active-session lock, timer deadlines, and rate-limit counters. Autosave writes go straight to Postgres (append checkpoint rows) — no write-behind cache to avoid loss.
3. **Session enforcement**: `exam_sessions` row with unique partial index on `(assignment_id) WHERE status='active'` + Redis lock `session:{assignment_id}` for fast rejection.
4. **Versioning**: publishing creates `assessment_versions` (deep JSONB snapshot + relational copies of sections/question refs). A `started_count > 0` guard makes edits fork a new version automatically.
5. **Timers**: server stores absolute deadlines (`section_deadline_at`); WS pushes authoritative remaining-time on connect/reconnect and at drift-correction intervals; expiry enforced by an ARQ cron sweep + lazy check on every exam API call (belt and suspenders).
6. **Proctoring pipeline**: browser captures webcam frames → pre-signed PUT to S3 → event POST with object key → ARQ AI-analysis job (sampled, not every frame) → flags on session.
7. **AI abstraction**: single `services/ai/` boundary using the Gemini API (`google-genai` SDK, `GEMINI_API_KEY`); all outputs stored with prompt/model/version; feature-flagged per capability.
8. **Audit**: FastAPI dependency + service-layer helper writes audit rows in the same transaction as the mutation; DB role separation guarantees immutability.
9. **Email**: ARQ jobs call Resend; webhook endpoint updates `email_messages.status`; reminders scheduled by an ARQ cron job scanning upcoming assignments.
10. **Background jobs — ARQ instead of Celery**: single async stack (FastAPI + asyncpg + ARQ all on asyncio), Redis-native, cron support built in; one worker process type, far less operational surface than Celery + beat.

## Phase 0: Outline & Research → `research.md` (complete)
## Phase 1: Design & Contracts → `data-model.md`, `contracts/`, `quickstart.md` (complete)

## Phase 2: Task Planning Approach

Tasks generated from contracts (contract-test task per endpoint group), data model (model + migration task per aggregate), and user stories (integration tests). TDD order: contract → integration → unit; dependency order: infra → models → services → endpoints → FE. [P] marks parallelizable tasks (different files, no dependency). Output: `tasks.md` with ~90 numbered tasks across 8 milestones.

## Complexity Tracking

*No constitution violations — table empty.*

## Progress Tracking

- [x] Phase 0: Research complete
- [x] Phase 1: Design complete (data-model, contracts, quickstart)
- [x] Phase 2: Task planning complete (tasks.md generated)
- [ ] Phase 3: Implementation
- [ ] Phase 4: Validation (quickstart smoke test, perf check vs NFRs)

**Initial Constitution Check**: PASS | **Post-Design Constitution Check**: PASS

---
*Based on Constitution v1.0.0 — see `.specify/memory/constitution.md`*
