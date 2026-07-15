# TestBuilder — Online Assessment Platform

Admin-driven candidate assessment platform: versioned test builder, question bank with
AI generation (Google Gemini), per-assessment candidate management with bulk import,
proctored timed exams with a sandboxed coding engine (Judge0), AI-assisted evaluation
with human override, and immutable audit logging.

Built from the spec in [`specs/001-testbuilder-platform/`](specs/001-testbuilder-platform/spec.md)
(spec-kit format: spec → plan → research → data-model → contracts → testing-strategy → tasks).

## Stack

- **Backend**: FastAPI + SQLAlchemy 2 (async) + Pydantic v2, Argon2id + rotating JWT
  refresh tokens, structlog. PostgreSQL in production, SQLite for zero-setup dev.
- **Frontend**: Next.js 15 + TypeScript + Tailwind + shadcn/ui, TanStack Query,
  Monaco editor. Jest + React Testing Library.
- **Services**: Judge0 CE (code execution), Google Gemini via `google-genai`
  (AI features), Resend (email), S3/MinIO (evidence storage), Redis (production
  locks/queues). Every service has a safe local fallback so the whole product runs
  with no external dependencies.

## Quick start (zero dependencies)

```bash
# backend — http://localhost:8000 (docs at /docs)
cd backend
uv sync --all-extras
uv run python -m testbuilder.seed        # admin@example.com / Admin!Passw0rd
uv run uvicorn testbuilder.main:app --port 8000

# frontend — http://localhost:3000
cd frontend
npm install
npm run dev
```

Sign in at `http://localhost:3000/admin/login`, build + publish an assessment, add a
candidate (credentials are shown once and "emailed" to the console), then take the
exam at `http://localhost:3000/candidate/login`.

Without configuration the following fallbacks are active (see `backend/.env.example`):

| Service    | Fallback                                                        |
| ---------- | --------------------------------------------------------------- |
| PostgreSQL | SQLite file `backend/testbuilder.db`                            |
| Gemini     | Deterministic stub (drafts still gated behind approval)         |
| Judge0     | Fail-closed stub — code never executes on the app host          |
| Resend     | Console transport (emails logged, marked sent)                  |
| S3         | Local disk `backend/storage_local/`                             |

## Full local stack (Docker)

```bash
docker compose -f infra/docker-compose.yml up -d   # postgres, pgbouncer, redis, minio, judge0
cd backend
uv run alembic upgrade head                        # apply schema to Postgres
uv run python -m testbuilder.seed
uv run uvicorn testbuilder.main:app --port 8000
```

`backend/.env` (gitignored) points the API at the compose services:
Postgres on host port **15432** (5432/5433 are commonly taken by native installs),
Judge0 on **2358**, Redis on **6379**, MinIO on **9000** (console **9001**).
Add your own `TB_S3_*`, `TB_GEMINI_API_KEY`, and `TB_RESEND_API_KEY` to enable
object storage, real AI, and real email — everything else falls back safely.

Schema changes go through Alembic: `uv run alembic revision --autogenerate -m "..."`
then `uv run alembic upgrade head`.

## Email setup (Resend)

Without a key, emails print to the backend console (dev mode). To send real email:

1. Create a free account at [resend.com](https://resend.com) → **API Keys** → create a key.
2. **Domains** → add your domain and create the DNS records Resend shows you
   (SPF + DKIM, usually 3 records). Wait for "Verified" — this is what makes
   delivery reliable and keeps you out of spam.
3. In `backend/.env` set:
   ```
   TB_RESEND_API_KEY=re_xxxxxxxxxxxx
   TB_EMAIL_FROM=TestBuilder <invites@yourdomain.com>   # must be on the verified domain
   TB_FRONTEND_BASE_URL=https://your-app-url            # used for the sign-in link
   ```
4. Restart the backend. Invitations, resends and credentials all include the
   sign-in link, the candidate's email and their one-time password. Delivery
   status is tracked per candidate under the assignment's email history.

If you have no domain yet, Resend lets you send from `onboarding@resend.dev`
to your own inbox only — enough for testing.

## Question JSON import format

Admins can bulk-import questions (Question Bank → *Import JSON*). Everything
imports as **drafts** that must be approved. Download the exact template from
the UI (or `GET /api/v1/questions/import-template`). Shape:

```json
{
  "questions": [
    {
      "qtype": "mcq | text | coding",        // required
      "title": "Question title",              // required, min 3 chars
      "body": "Longer prompt (optional)",
      "difficulty": "easy | medium | hard",   // default medium
      "category": "Web", "topic": "http",
      "skills": ["backend"], "tags": ["rest"],
      "expected_duration_sec": 60,
      "answer_type": "single_choice | multi_choice | long_text | code",
      "config": {
        // mcq (any number of options, one or many correct):
        "options": [{"id": "a", "text": "..."}],
        "correct_option_ids": ["a"],
        // text:
        "rubric": "...", "expected_answer": "...",
        // coding (boilerplate the candidate completes + test cases):
        "allowed_languages": ["python", "javascript"],
        "starter_code": {"python": "def solve():\n    pass"},
        "test_cases": [
          {"id": "t1", "input": "...", "expected_output": "...",
           "is_hidden": false, "weight": 1}
        ]
      }
    }
  ]
}
```

Invalid entries are reported per index with the reason; valid ones import anyway.

## Candidate CSV import format

Admins can bulk-import candidate details from the assessment's **Candidates** tab.
Use these exact column names and save the file as UTF-8 CSV:

```csv
studentId,name,email,phone,cgpa
STU-1001,Jane Doe,jane@example.com,+919876543210,8.75
STU-1002,Rahul Sharma,rahul@example.com,9876543210,9.10
```

`studentId`, `name`, `email`, and `cgpa` are required. CGPA must be between 0 and
10. `phone` is optional; when provided, use a 10-digit Indian mobile number with
an optional `+91` prefix. Test windows are not included in individual CSV rows;
every imported or manually added candidate inherits the assessment's fixed start
and end time.

Assessment start and end times are set when the assessment is created. Section
durations must add up to that exact window: for example, an assessment from 12:00
to 13:00 requires exactly 60 total section minutes. The backend prevents section
creation above the limit and prevents publishing when the total is below it.

## Tests

```bash
cd backend && uv run pytest        # 81 tests: unit + contract + integration (incl. time-travel timer tests)
cd backend && uv run ruff check src tests
cd frontend && npm test            # Jest + RTL component tests
cd frontend && npm run build       # type-check + lint + production build
```

## What's implemented (spec module map)

| Module | Highlights |
| --- | --- |
| 1. Admin/RBAC/Audit | 3 roles (union permissions), append-only audit log with before/after snapshots, filterable viewer |
| 2. Candidates | Per-assessment assignments, duplicate-email rejection, CSV/Excel import with per-row error report, per-assignment temporary credentials that expire with the window |
| 3. Auth & access | Server-IST window gating ("starts soon"/"expired"), one active session per assignment with heartbeat supersede, admin recovery sessions, rotating refresh tokens with reuse detection |
| 4. Test builder | Ordered weighted sections, freeze-on-first-start, edit-after-start forks a new version, publish validation (weightage=100, pool coverage), answer-of-record checkpoints |
| 5. Question bank | MCQ/text/coding with structural quality checks + duplicate detection; Gemini generation lands as `draft` and requires human approval |
| 6. Exam experience | Device check gate, rules acknowledgment, randomized questions/options (persisted per candidate), autosave, skip/revisit/mark-review palette, section auto-submit, success page |
| 7. Coding engine | Judge0 client (JS/Python/Java/C++/C), visible vs hidden cases, weighted partial credit, run/submit rate limits, full submission history |
| 8. Proctoring | Fullscreen/tab/blur/copy-paste/camera events with policy-based severity, periodic webcam screenshots, admin timeline + flags |
| 9. Evaluation & reports | Exact MCQ + test-case code scoring, AI text review with confidence, audited overrides, finalize lock, percentile gating (cohort ≥ 20), CSV export |
| 10. Email | Invitation/resend/reminders with delivery tracking; per-assignment toggle |

## Repository layout

```
backend/    FastAPI app (src/testbuilder), pytest suite (tests/)
frontend/   Next.js app (src/app admin + candidate, src/components, Jest tests)
infra/      docker-compose for postgres/pgbouncer/redis/minio/judge0
specs/      full spec-kit specification driving this implementation
```
