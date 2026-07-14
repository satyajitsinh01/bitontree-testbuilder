# Phase 0 Research: TestBuilder Platform

Decisions with rationale and alternatives considered. Format per spec-kit: Decision / Rationale / Alternatives.

---

## R1. Code execution engine

- **Decision**: Self-hosted **Judge0 CE** in Docker (isolate-based sandboxing), fronted by our own ARQ queue.
- **Rationale**: Battle-tested isolation (cgroups + isolate), native support for JS/Python/Java/C++/C, per-run CPU/memory/wall-time limits, no-network by default. Building a custom runner duplicates this with more risk.
- **Alternatives**: Custom Docker-per-run runner (more control, much more work — deferred; the `judge/` client module isolates us so a swap stays local); Piston (weaker limits configurability); cloud judges like Sphere Engine (cost, data residency).
- **Notes**: We still wrap Judge0 with our own queue + rate limiting (FR-067) so burst traffic queues in ARQ rather than overwhelming Judge0 workers. Judge0 callbacks (PUT webhook) preferred over polling.

## R2. One-active-session enforcement

- **Decision**: DB partial unique index `exam_sessions(assignment_id) WHERE status = 'active'` as the correctness guarantee; Redis key `lock:session:{assignment_id}` (TTL = heartbeat window) as the fast path; WS heartbeat every 15 s refreshes the lock.
- **Rationale**: DB constraint survives Redis flushes; Redis gives O(1) rejection without DB round-trip on login storms. Heartbeat TTL lets a crashed session become reclaimable (admin or auto after grace) without manual cleanup.
- **Alternatives**: Redis-only (lost on failover → double sessions); DB-only advisory locks (held per-connection, awkward with PgBouncer transaction pooling).
- **Policy default**: new login while a session is active → **rejected** with message; admin can force "new session" (FR-024) which terminates the old one. Configurable per assessment later if product wants "terminate old".

## R3. Server-authoritative timers over WebSocket

- **Decision**: Persist absolute deadlines (`window_end_at`, `section_deadline_at` computed at section start). Client gets `server_now` + deadlines on WS connect and every 30 s drift-sync; renders countdown locally. Expiry is enforced by (a) lazy check on every exam API call and (b) an ARQ cron sweep every 15 s that force-submits overdue sections/sessions.
- **Rationale**: WS alone can't be trusted (disconnects); lazy checks alone miss idle candidates; the sweep guarantees auto-submit (FR-036/037) even for disconnected candidates.
- **Alternatives**: Client-reported timers (violates Constitution I); per-session asyncio timers in API process (lost on restart/scale-out).

## R4. Assessment versioning model

- **Decision**: `assessments` (mutable draft head) + `assessment_versions` (immutable published snapshots: relational copies of sections + question-version references + rules, plus a JSONB render snapshot). `exam_sessions.assessment_version_id` pins each candidate. First candidate start sets `versions.frozen = true`; any edit to a frozen version's assessment auto-creates version n+1 as the new draft/published head.
- **Rationale**: Relational copies keep scoring queries relational; JSONB snapshot gives cheap, exact reproduction of what the candidate saw. Question edits create `question_versions`, so bank edits never mutate a live exam.
- **Alternatives**: Event-sourcing (overkill); copy-on-write of whole assessment rows only (loses question immutability).

## R5. Autosave & answer-of-record

- **Decision**: Client debounces input 2 s (and flushes on blur/navigation). Each save is an idempotent upsert into `answers` (latest state) plus an append into `answer_checkpoints` for the checkpoint events: `next_question`, `run_code`, `submit_code`, `autosave` (autosave checkpoints sampled, others always). Final answer = latest checkpoint at submission time.
- **Rationale**: Meets NFR-002 (≤ 3 s loss), gives the audit/history the spec demands for code (run/submit with timing and test cases), keeps hot-path writes small.
- **Alternatives**: Redis write-behind (risk of loss on failover — rejected); full event log per keystroke (volume without value).

## R6. Temporary candidate credentials

- **Decision**: Per-assignment username (`{shortcode}-{seq}` e.g. `BES24-0173`) + 12-char random password, Argon2id-hashed; plaintext delivered only in the invitation email (and one-time reveal to admin at creation). Login issues an assignment-scoped JWT whose `exp = min(now+15m, assignment.window_end_at)`; refresh token likewise capped at window end. A daily job (and lazy check) marks credentials expired after window end.
- **Rationale**: Meets FR-016/017/026 with zero shared secrets across assessments; token-exp capping means even a stolen token dies with the window.
- **Alternatives**: Magic links (email access risk in proctored settings, resend friction); OTP per login (SMS cost, delivery latency during exam start spikes).

## R7. Bulk import (CSV/Excel)

- **Decision**: Upload to S3 via pre-signed URL → ARQ job parses with `openpyxl`/`csv`, validates per row (email format, phone, window sanity, duplicate-in-file, duplicate-in-assessment), inserts valid rows, returns downloadable error report (same file + `error` column). Progress via polling endpoint.
- **Rationale**: Keeps large files off the API workers; per-row error report matches FR-012; partial success is explicit.
- **Alternatives**: Synchronous parse (times out at 10k rows); all-or-nothing transaction (one typo blocks 4,999 rows — rejected by spec).

## R8. Proctoring capture & analysis

- **Decision**: Browser `getUserMedia` → canvas frame JPEG every 5 s (configurable) → pre-signed PUT direct to S3 → lightweight event POST with the object key. AI analysis runs async in an ARQ job on a **sample** (e.g., 1 frame / 30 s, plus every frame around suspicious events), not every frame. Behavioral events (tab switch, blur, fullscreen exit, copy/paste, permission loss) fire from FE listeners immediately over WS with REST fallback.
- **Rationale**: Direct-to-storage uploads keep the API out of the hot path; sampling controls AI cost while dense capture preserves evidence; WS gives admins a live timeline.
- **Alternatives**: Continuous video recording (storage + privacy cost, v2 candidate); analyzing every frame (cost without proportional signal).

## R9. AI provider & guardrails

- **Decision**: **Google Gemini API** via the official `google-genai` Python SDK, authenticated with a Gemini API key (`GEMINI_API_KEY` env var), behind `services/ai/` with one function per capability (generate_questions, evaluate_written, analyze_frames, summarize_performance). Text capabilities use a Gemini text model with structured (JSON-schema) output; screenshot analysis uses Gemini multimodal input (image + prompt). Every call stores prompt, model id, params, and raw response ref. Question generation always lands as `draft` (FR-043). Written-answer eval returns score + rationale + confidence; low confidence auto-queues for human review.
- **Rationale**: Single SDK covers text, structured output, and vision (proctoring screenshots); API-key auth keeps setup simple (no GCP service-account plumbing needed for the Developer API); the `services/ai/` seam keeps the provider swappable and every output reproducible/auditable; human-in-the-loop satisfies Constitution V.
- **Alternatives**: Anthropic Claude / OpenAI (equally capable — Gemini chosen as the mandated provider); Vertex AI entry point (adds GCP project/IAM overhead, not needed for API-key usage); direct calls scattered in routes (untestable, unauditable); self-hosted models (ops burden).

## R10. Email pipeline

- **Decision**: Resend via ARQ jobs; `email_messages` table tracks lifecycle; Resend webhooks (delivered/bounced/complained) update status. Reminders: ARQ cron every 5 min scans assignments with `start_at` in the 24 h / 1 h reminder buckets not yet reminded and not completed.
- **Rationale**: Meets FR-090..094 with observable delivery; beat-scan is simpler and more robust than per-candidate scheduled tasks (reschedules just work — the scan reads current timings).
- **Alternatives**: Per-assignment deferred jobs with fixed ETAs (orphaned on reschedule); polling Resend API for status (webhooks are push and cheaper).

## R11. Randomization (questions, options, pools)

- **Decision**: At exam session creation, compute and persist the candidate's concrete question list: apply pool rules ("random 10 of 30") and shuffles using seed = `hash(session_id)`, store as `session_questions` rows (order index + option order JSON).
- **Rationale**: Persisted selection makes revisits/reconnects stable (FR-052), scoring reproducible, and disputes resolvable; seeded RNG makes it re-derivable.
- **Alternatives**: Shuffle client-side (tamperable); recompute per request (unstable on reconnect).

## R12. PgBouncer & async SQLAlchemy

- **Decision**: PgBouncer in transaction-pooling mode; SQLAlchemy async engine with `pool_pre_ping`, no server-side prepared statements (asyncpg `statement_cache_size=0`); no session-level advisory locks (see R2).
- **Rationale**: Transaction pooling maximizes exam-spike throughput; the constraints above are the known sharp edges.
- **Alternatives**: Session pooling (fewer gotchas, far fewer effective connections).

## R13. Report exports

- **Decision**: PDF via headless Chromium (Playwright) rendering the same React report view server-side in an ARQ job; CSV/Excel via `openpyxl`. Artifacts stored in S3 with signed download URLs.
- **Rationale**: One source of truth for report layout (the web view); async generation keeps API snappy.
- **Alternatives**: reportlab/WeasyPrint (duplicate layout maintenance).

## R14. Frontend exam-state management

- **Decision**: TanStack Query for server state with mutation queue for autosave (offline buffer + replay on reconnect); React Hook Form + Zod per question form; a thin `useExamSession` context for timer/WS/proctor state. No global state library.
- **Rationale**: Query's mutation retry/queue covers flaky networks (NFR-002); avoids Redux ceremony per Constitution VII.
- **Alternatives**: Redux Toolkit (unneeded); localStorage-only buffering (kept as secondary crash buffer, not primary).

## R15. Quality checks for questions (FR-047)

- **Decision**: On create/approve: (a) structural validation in Pydantic (MCQ needs ≥2 options and ≥1 correct; coding question's reference solution must pass its own test cases via a Judge0 dry run); (b) duplicate detection via pg_trgm similarity ≥ 0.85 against active bank; (c) AI check for ambiguity/bias returning advisory flags shown to the approver.
- **Rationale**: Hard checks block structurally broken questions; soft checks inform the human, aligning with Constitution V.
- **Alternatives**: Embedding-based dedupe (better recall, adds a vector store — v2).

## R16. Background jobs — ARQ, not Celery

- **Decision**: **ARQ** (async Redis queue, from the pydantic/uvicorn author) for all background work: email sends, bulk-import parsing, AI jobs (generation, written eval, frame analysis, summaries), report/PDF generation, Judge0 dispatch, and cron sweeps (timer expiry every 15 s, reminder scan every 5 min, credential expiry, evidence retention purge).
- **Rationale**: The whole backend is asyncio (FastAPI + asyncpg + httpx); ARQ jobs share that model and can reuse the same async SQLAlchemy/service code without sync bridges. Redis is already in the stack as broker. Built-in cron removes the separate beat process — one worker process type instead of Celery worker + beat. Job retries, deferred jobs, and result storage cover every need in this spec.
- **Alternatives**: Celery (sync-first, needs worker + beat processes, heavier ops surface — explicitly removed); Dramatiq (solid but sync-first); FastAPI BackgroundTasks (in-process only — dies with the request worker, no retries/cron; unacceptable for durability requirements like FR-036/037).

## R17. Frontend design system — shadcn/ui professional admin UI

- **Decision**: shadcn/ui is the single source of UI primitives for both the admin panel and the candidate exam shell. Admin panel uses the shadcn **Sidebar + breadcrumb app-shell** pattern; all lists are shadcn **DataTable** (TanStack Table: server pagination, sorting, filtering, column visibility, row actions); forms use shadcn Form (RHF + Zod); overlays use Dialog/Sheet/AlertDialog (destructive confirmations); feedback via Sonner toasts; dashboards use shadcn Charts (Recharts); Command palette (⌘K) for admin navigation. Theme tokens (CSS variables in `globals.css`) define brand colors, radius, and typography; light + dark mode via `next-themes`. Exam UI reuses the same tokens with a distraction-free layout (no sidebar, timer/progress in a fixed header).
- **Rationale**: One component vocabulary keeps the product visually professional and consistent; shadcn components are owned code (copied in), so no upstream lock-in; accessibility (Radix primitives) supports NFR-008.
- **Alternatives**: MUI/Ant (heavier, harder to brand); Tailwind-only bespoke components (inconsistent, slower); Tremor (dashboard-only).
