# Tasks: TestBuilder — Online Assessment Platform

**Input**: Design documents from `specs/001-testbuilder-platform/` (plan.md, research.md, data-model.md, contracts/, testing-strategy.md)
**Convention**: `[P]` = parallelizable (different files, no unmet dependency). TDD: contract/integration tests are written and observed failing before their implementation task. Paths per plan.md structure.
**Testing**: every milestone carries its module's three test levels from testing-strategy.md — the milestone's contract-test task implements the `FT-Mx-*` functional cases, a dedicated unit-test task implements `UT-Mx-*`, and Milestone K implements the `FE-Mx-*` Playwright feature specs plus cross-cutting suites. A milestone is not done until its UT + FT cases pass in CI.

---

## Milestone A — Foundation & Infrastructure

- [ ] **T001** Create monorepo skeleton: `backend/` (uv + pyproject.toml, Ruff config), `frontend/` (npm, Next.js 15 + TS + Tailwind + shadcn/ui init, ESLint/Prettier, Jest config), `infra/`
- [ ] **T002** `infra/docker-compose.yml`: postgres:16, pgbouncer (transaction pooling), redis:7, judge0 CE (server + workers, no-network), minio
- [ ] **T003** [P] Backend app factory: FastAPI app, pydantic-settings `config.py`, structlog with request-id middleware, `/health`, error envelope handler
- [ ] **T004** [P] Async SQLAlchemy engine + session dependency (asyncpg, `statement_cache_size=0` per R12); Alembic init with IST-aware `timestamptz` defaults
- [ ] **T005** [P] CI pipeline: lint (Ruff/ESLint), type-check (mypy/tsc), pytest, Jest, `alembic upgrade --sql` check
- [ ] **T006** [P] AWS S3 storage module (boto3): pre-signed PUT/GET helpers, bucket layout (`imports/`, `evidence/`, `exports/`, `ai/`); MinIO endpoint override for dev
- [ ] **T007** [P] ARQ worker setup in `workers/` (R16): WorkerSettings, Redis connection, job base with structlog + retry policy, cron registration
- [ ] **T008** [P] FE design system baseline (R17): shadcn theme tokens in `globals.css` (brand colors, radius, typography), dark mode via next-themes, Sidebar app-shell + breadcrumb layout for admin, Sonner toaster, Command palette scaffold

## Milestone B — Identity, RBAC & Audit (Module 1)

- [ ] **T009** Test harness (testing-strategy §1/§4): pytest conftest with transactional-DB fixture, factory_boy factories, time-machine clock, FakeJudge0/FakeGemini/FakeResend stubs, ARQ burst mode; FE: Jest + RTL + MSW setup
- [ ] **T010** Contract/functional tests FT-M1-01…05 for `/auth/admin/*`, `/admin/users`, `/admin/audit-logs` per api-contracts.md §1–2
- [ ] **T011** Models + migration: organizations, users, user_roles, refresh_tokens, audit_logs (INSERT/SELECT-only grant for app role — separate migration executed as superuser)
- [ ] **T012** Auth service: Argon2id hashing, JWT issue/verify (≤15 min), refresh rotation with family reuse-detection (FR-025)
- [ ] **T013** RBAC dependency: role-union permission check per route group (FR-002/003); org scoping dependency
- [ ] **T014** Audit service: same-transaction `audit_logs` writer with before/after snapshots + request context (FR-005/006); unit tests proving no update/delete path
- [ ] **T015** Admin users CRUD endpoints + audit-log viewer endpoint with filters (FR-007)
- [ ] **T016** [P] FE: admin login page, auth provider (TanStack Query + refresh flow), role-gated layout/navigation
- [ ] **T017** [P] FE: admin users management page; audit log viewer with filters
- [ ] **T018** [P] Unit tests UT-M1-01…05: Argon2 roundtrip, JWT expiry/tamper, refresh-family reuse revocation, RBAC union, audit writer transactionality

## Milestone C — Question Bank & AI Generation (Module 5)

- [ ] **T020** Contract/functional tests FT-M5-01…05 for `/questions*` per api-contracts.md §3
- [ ] **T021** Models + migration: questions, question_versions, ai_generations, question_quality_flags (data-model §2)
- [ ] **T022** Question service: create/edit-as-new-version/status transitions/tagging; block activation of unapproved AI drafts (FR-041/043)
- [ ] **T023** Quality checks (FR-047): Pydantic structural validation per qtype; pg_trgm duplicate detection; coding reference-solution dry-run against Judge0 (behind flag until T060)
- [ ] **T024** AI generation: `services/ai/generation.py` (Gemini via `google-genai` SDK + `GEMINI_API_KEY`, structured JSON output, provider seam per R9) + ARQ job + generation status endpoint; outputs land as `draft` with stored prompt/model (FR-042/045)
- [ ] **T025** Approve/reject workflow endpoints with audit logging (FR-044)
- [ ] **T026** [P] FE: question bank list/filter page, question editor (per-type forms: MCQ options+correct, text rubric, coding starter/test cases via RHF+Zod)
- [ ] **T027** [P] FE: AI generation dialog (prompt → progress → draft review queue with edit/approve/reject)
- [ ] **T028** [P] Unit tests UT-M5-01…06: MCQ/coding structural validation, trigram dedupe, edit-as-version, seeded pool selection (stability + distribution), Gemini response parsing incl. malformed JSON

## Milestone D — Test Builder & Versioning (Module 4)

- [ ] **T030** Contract/functional tests FT-M4-01…05 for `/assessments*`, `/sections*` per api-contracts.md §4 (incl. edit-after-start fork and clock-jump auto-submit cases)
- [ ] **T031** Models + migration: assessments, assessment_versions, sections, section_questions, section_pool_rules (+ frozen-version UPDATE-guard trigger)
- [ ] **T032** Versioning service (R4): draft head editing, freeze-on-first-start, auto-fork on edit of frozen version (FR-034); unit tests for fork semantics
- [ ] **T033** Section CRUD + question/pool-rule assignment endpoints
- [ ] **T034** Publish endpoint with validations: pool coverage, Σ weightage = 100, durations > 0, final-section flag (FR-038, FR-033)
- [ ] **T035** [P] FE: test builder — assessment form, drag-ordered section list, section config panel, question picker (bank search + pool grouping), publish flow with validation errors
- [ ] **T036** [P] FE: version history view
- [ ] **T037** [P] Unit tests UT-M4-01…05: publish validations, fork semantics, freeze-guard trigger, section reorder invariants, answer-of-record checkpoint resolution

## Milestone E — Candidates, Assignments & Email (Modules 2, 10)

- [ ] **T040** Contract/functional tests FT-M2-01…06 and FT-M10-01…03 for §5 (assignments, import) and §10 (emails)
- [ ] **T041** Models + migration: candidates, test_assignments (unique constraints per FR-013/014), import_batches, email_messages
- [ ] **T042** Credentials service (R6): username generation, random password, Argon2id, one-time reveal, expiry job + lazy expiry (FR-016/017)
- [ ] **T043** Assignment endpoints: add (409 on duplicate), edit/reschedule, remove (confirm if in-progress), all audit-logged (FR-011/015)
- [ ] **T044** Bulk import (R7): presign upload, ARQ parse/validate job, per-row error report generation, progress endpoint, template download (FR-012/013)
- [ ] **T045** Email service + ARQ jobs: invitation template (link, credentials, window + timezone, duration, rules, requirements — FR-020), resend single/bulk, send_email toggle (FR-018), Resend webhook → status updates (FR-094)
- [ ] **T046** Reminder cron job (ARQ): 24 h / 1 h buckets, skips completed/removed (FR-093)
- [ ] **T047** [P] FE: candidates tab inside assessment — table with statuses/email status, add-candidate dialog, import wizard (upload → progress → error report download), reschedule/resend/remove actions
- [ ] **T048** Integration test: User Story 1 admin flow (create → import → invite → monitor list)
- [ ] **T049** [P] Unit tests UT-M2-01…04 + UT-M10-01…03: credential generation/expiry, import row validation, in-file dedupe, reminder bucketing, template rendering fail-fast, webhook status mapping

## Milestone F — Candidate Auth, Sessions & Exam Runtime (Modules 3, 6)

- [ ] **T050** Contract/functional tests FT-M3-01…04 and FT-M6-01…06 for `/auth/candidate/*` and `/exam/*` per §1, §6 (incl. racing double-login and the data-leakage schema guard)
- [ ] **T051** Models + migration: exam_sessions (partial unique active index), session_sections, session_questions, answers, answer_checkpoints
- [ ] **T052** Candidate login: window gating vs server IST with `window_not_started`/`window_expired` responses (FR-021/022), assignment-scoped JWT capped at window end (FR-026)
- [ ] **T053** Session service (R2): active-session enforcement (DB index + Redis lock + heartbeat TTL), admin recovery-session endpoint terminating prior session (FR-023/024)
- [ ] **T054** Exam start: rules acknowledgment, session creation, seeded pool selection + question/option shuffle persisted to session_questions (R11, FR-046/052)
- [ ] **T055** Exam runtime endpoints: state/resume, section questions, autosave answer upsert + checkpoint appends (`next_question`), mark-review, section submit, final submit with confirmation (FR-035/053/055/057)
- [ ] **T056** Timer enforcement (R3): absolute deadlines on session_sections, lazy expiry checks on every exam call, ARQ cron sweep force-submitting overdue sections/sessions (FR-036/037/056)
- [ ] **T057** WebSocket `/ws/exam` per ws-contracts.md: auth, heartbeat/lock refresh, `session.state` sync, expiry pushes, supersede handling
- [ ] **T058** [P] FE: candidate login + "starts soon"/"expired" screens with countdown; device-check page (camera, mic, network probe, browser matrix, fullscreen test) gating Start (FR-050/051)
- [ ] **T059** [P] FE: exam shell — question renderer per type, section timer (server-synced), progress palette (attempted/unattempted/marked), free navigation, `useAutosave` (debounce + offline mutation queue), auto-submit UX, success page
- [ ] **T05A** Integration test: User Story 2 — full candidate flow incl. refresh-resume, duplicate-login rejection, section timeout auto-advance
- [ ] **T05B** [P] Unit tests UT-M3-01…04 (window boundaries, JWT window cap, session lock TTL, invitation renderer) + UT-M6-01…05 (useAutosave debounce/offline-replay, useServerTimer drift, progress palette, device-check gating, option-shuffle render — Jest)

## Milestone G — Coding Engine (Module 7)

- [ ] **T060** Contract/functional tests FT-M7-01…06 for §7 code endpoints (visible-vs-hidden masking, rate limit, callback HMAC)
- [ ] **T061** Models + migration: code_submissions; Judge0 client module (`judge/`): language mapping, batched per-case submissions, HMAC-verified callback endpoint
- [ ] **T062** Run/submit endpoints: rate limiting in Redis (FR-067), queueing via ARQ, visible-vs-hidden case handling, result mapping (compile/runtime/timeout), per-case weighted scoring (FR-062..066)
- [ ] **T063** Checkpoint integration: run/submit create answer_checkpoints with timing + results (FR-035); WS `code.result` push
- [ ] **T064** [P] FE: Monaco editor component — language selector, starter code, run panel (visible cases, stdout/stderr/errors), submit with per-config result display
- [ ] **T065** Enable T023 reference-solution dry-run in question quality checks
- [ ] **T066** Load test script: 200 concurrent submissions → queue depth + wait metrics vs NFR-004
- [ ] **T067** [P] Unit tests UT-M7-01…04: language mapping, judge0 status/result mapping with truncation, weighted scorer (partial credit on/off), sliding-window rate limiter

## Milestone H — Proctoring (Module 8)

- [ ] **T070** Contract/functional tests FT-M8-01…04 for §8 proctoring endpoints (incl. retention purge with clock jump)
- [ ] **T071** Models + migration: proctoring_events, proctoring_evidence; retention purge cron job (NFR-006)
- [ ] **T072** Ingest: WS `proctor.event` + REST batch fallback; evidence presign + registration flow (R8); `capture_failed` handling (FR-072)
- [ ] **T073** [P] FE: ProctorGuard hooks — fullscreen enforcement + re-entry prompt, visibilitychange/blur, copy/paste interception, camera/mic permission watchers, periodic webcam frame capture → direct S3 upload (FR-070..072)
- [ ] **T074** AI analysis ARQ job (Gemini multimodal, R9): sampled frame analysis → face-missing/multiple-faces/gaze/object flags with confidence; severity mapping to warning/red_flag (FR-074)
- [ ] **T075** [P] FE admin: per-candidate proctoring timeline (events + evidence thumbnails), flags panel; live monitor via `/ws/admin/assessments/{id}` (FR-075)
- [ ] **T076** Proctoring policy modes (strict/standard/lenient) wired from assessment settings (FR-076)
- [ ] **T077** [P] Unit tests UT-M8-01…05: ProctorGuard hooks (Jest), capture retry → capture_failed, policy severity mapper, Gemini analysis parser confidence thresholds, timestamp clamping

## Milestone I — Evaluation & Reports (Module 9)

- [ ] **T080** Contract/functional tests FT-M9-01…05 for §9 endpoints (auto-eval trigger, override authz, finalize lock, exports)
- [ ] **T081** Models + migration: evaluations, reports
- [ ] **T082** Auto-scoring service: MCQ exact (single/multi, optional negative marking — FR-080), coding from final submitted checkpoint (FR-081); triggered on session submit
- [ ] **T083** AI written-answer evaluation ARQ job (Gemini, R9): rubric-based score + rationale + confidence; low-confidence → review queue (FR-082)
- [ ] **T084** Evaluator override endpoint with mandatory reason + audit log (FR-083); report finalize
- [ ] **T085** Report compilation: overall/section scores with durations, attempted/right/wrong, code history, proctoring timeline, AI observations (FR-084/088); percentile/rank gated at cohort ≥ threshold (FR-087)
- [ ] **T086** Exports: PDF via headless-Chromium ARQ job, assessment CSV/Excel (R13, FR-086)
- [ ] **T087** [P] FE: results dashboard (assessment → candidates → detail click-through per FR-085), report view (scores, timeline, code history, AI sections labeled), override dialog, export buttons
- [ ] **T088** Integration test: User Story 4 — auto-scores + AI suggestion + override + finalized report + audit trail
- [ ] **T089** [P] Unit tests UT-M9-01…06: MCQ scorer variants (multi-correct, negative marking, unanswered), weightage aggregation, right/wrong counting, percentile gate + tie ranking, AI eval parser, override rule transactionality

## Milestone J — Hardening & Polish

- [ ] **T090** [P] Rate limiting middleware for auth/exam paths; idempotency-key support on exam mutations
- [ ] **T091** [P] Observability: metrics (queue depth, exec latency, WS connections, email failures), alert rules (runner outage, email failure spike) (NFR-007)
- [ ] **T092** [P] Security pass vs NFR-005: OWASP ASVS L2 checklist, signed-URL TTLs, upload validation, CORS/CSP headers, dependency audit
- [ ] **T093** [P] Accessibility pass (WCAG 2.1 AA) on admin + candidate UI where proctoring-compatible (NFR-008)
- [ ] **T094** Performance validation: 1k-concurrent exam-path load test vs NFR-001/002; tune PgBouncer/pool sizes
- [ ] **T095** Execute quickstart.md 14-step smoke test end-to-end; fix gaps
- [ ] **T096** [P] Seed script + demo dataset; `.env.example` files; ops runbook for Judge0 and Resend outages

## Milestone K — Feature (E2E) & Cross-Cutting Test Suites  *(testing-strategy §2 FE-\* and §3; starts as soon as the flows it covers exist — TK02 after E, TK05 after F, etc.)*

- [ ] **TK01** Playwright setup: compose test stack (Postgres, Redis, MinIO, Judge0, FakeGemini/FakeResend containers), auth helpers, `@module-N`/`@story-N` tags, CI stage 4 wiring
- [ ] **TK02** [P] FE-M1-01/02 + FE-M2-01…03: admin RBAC navigation, audit trail visibility; import wizard with error report, duplicate-email inline error, reschedule/resend flows
- [ ] **TK03** [P] FE-M3-01…03: early/late login screens with countdown, second-device rejection, admin session reset + resume with answers intact
- [ ] **TK04** [P] FE-M4-01/02 + FE-M5-01: build-and-publish story with validation errors; mid-test edit creates v2; AI draft → approve → pool rule → two candidates get different stable question sets
- [ ] **TK05** [P] FE-M6-01/02: full exam run (device check, skip/revisit/mark, palette, refresh persistence, section timeout, submit-and-end); 10 s network kill with ≤ 3 s loss
- [ ] **TK06** [P] FE-M7-01/02: coding question run/submit cycle with language switch; section expiry during in-flight run
- [ ] **TK07** [P] FE-M8-01/02: tab-switch/fullscreen warnings + live admin monitor; strict vs standard camera-loss policy
- [ ] **TK08** [P] FE-M9-01/02 + FE-M10-01: evaluator override → finalize → PDF export; percentile gating at cohort 20; bounced-email fix + resend chip
- [ ] **TK09** Security suite (testing-strategy §3): endpoint × role authz matrix (table-driven, fails on unclassified new endpoints), IDOR probes across candidate tokens, auth/exam rate-limit tests, signed-URL TTL expiry
- [ ] **TK10** [P] Timezone/clock suite: IST boundary parametrization, ±12 h client skew, exactly-at-start/exactly-at-end window edges
- [ ] **TK11** [P] Concurrency suite: racing double login/start/submit, simultaneous autosaves with idempotency, parallel imports with overlapping emails
- [ ] **TK12** [P] WS contract suite: auth, heartbeat lock refresh, supersede 4001, reconnect state replay, `section.expired` push
- [ ] **TK13** Nightly load suite (k6/locust): 1k concurrent answer-saves p95 < 300 ms (NFR-001), code-submission queue metrics (NFR-004); publish trend report
- [ ] **TK14** Coverage gates in CI: backend `services/` ≥ 85% branch, frontend `hooks/` + `components/exam/` ≥ 80%; FR→test traceability check against testing-strategy §5

---

## Dependencies (summary)

- A → everything. B → C,D,E (auth/audit are cross-cutting). C → D (builder picks questions). D,E → F (sessions need versions + assignments). F → G,H (exam runtime hosts code + proctoring). F,G,H → I (reports aggregate all). J last. K's per-module specs (TK02…TK08) start as soon as the milestone they cover ships; TK09–TK14 need F; TK13/TK14 gate release alongside J.
- Within milestones: contract-test task precedes its implementation tasks; models precede services precede endpoints; FE tasks [P] once their endpoints exist; the milestone's unit-test task ([P]) runs alongside implementation and must be green before the milestone closes.

## Parallel execution example

After T051–T057 land, run concurrently: T058, T059 (FE exam), T060-series (coding engine BE), T070-series (proctoring BE) — disjoint files, no shared migrations in flight.

## Validation checklist

- [x] Every contract group has a functional/contract-test task implementing its FT-Mx-* cases
- [x] Every module has a unit-test task implementing its UT-Mx-* cases (T018, T028, T037, T049, T05B, T067, T077, T089)
- [x] Every module has feature/E2E coverage via FE-Mx-* Playwright specs (TK02…TK08)
- [x] Every data-model aggregate has a model+migration task
- [x] Every primary user story has an integration test (T048, T05A, T088; Story 3 covered by T024–T027 + C-milestone tests) and an E2E story spec in Milestone K
- [x] All FR-/NFR-IDs traceable to at least one task and to test IDs per testing-strategy.md §5
