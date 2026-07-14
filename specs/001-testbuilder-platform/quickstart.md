# Quickstart: TestBuilder Platform

Dev environment setup and the end-to-end smoke test that validates the primary user stories.

## Prerequisites

- Docker Desktop (Compose v2)
- Node 20 LTS + npm (no pnpm/yarn — org standard)
- Python 3.12 + `uv`
- A Resend API key (or leave unset → emails log to console in dev)
- A Google Gemini API key (`GEMINI_API_KEY`, from Google AI Studio) for AI features (or unset → AI features return stub drafts in dev)

## 1. Infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d
# starts: postgres:16, pgbouncer, redis:7, judge0 (server+workers), minio (S3-compatible dev storage)
```

## 2. Backend

```bash
cd backend
uv sync                       # install deps from pyproject.toml
cp .env.example .env          # DB/Redis/Judge0/MinIO defaults point at compose services
uv run alembic upgrade head   # apply migrations
uv run python -m testbuilder.seed   # seed org + admin (admin@example.com / see console) + sample questions
uv run uvicorn testbuilder.main:app --reload --port 8000
# background worker (separate terminal — ARQ handles jobs AND cron sweeps in one process):
uv run arq testbuilder.workers.WorkerSettings
```

Verify: `http://localhost:8000/docs` shows the OpenAPI UI; `GET /api/v1/health` → `{"status":"ok"}`.

## 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run gen:api               # generate typed client from backend OpenAPI
npm run dev                   # http://localhost:3000
```

## 4. Tests

```bash
cd backend && uv run pytest             # contract + integration + unit
cd frontend && npm test                 # Jest + RTL
```

## 5. End-to-end smoke test (validates primary stories)

1. **Admin login** at `/admin` with the seeded credentials.
2. **Create assessment** "Smoke Test" → add sections: "MCQ" (10 min, 40%, 3 questions), "Coding" (20 min, 60%, 1 question, final).
3. **Question bank**: add 3 MCQs manually; run **AI generate** for 2 more → confirm they land as *draft* and are unselectable → approve one → attach questions to sections (pool rule: pick 3 of 4 for MCQ section).
4. **Publish** → expect validation pass (weightage 100%, coverage ok).
5. **Add candidate** with your email, window = now → now + 2 h, send_email on → check invitation (Resend or console) contains link, credentials, window, duration, rules.
6. **Duplicate check**: add the same email again → expect `409 duplicate_email_in_assessment`.
7. **Bulk import**: upload the template with 3 rows (1 invalid email) → expect 2 imported, 1 in error report.
8. **Candidate login** (incognito) → device check (grant camera/mic, fullscreen) → Start.
9. During exam: answer an MCQ, refresh the page → answer persists (autosave); open a second tab and log in again → rejected (one active session); switch tabs → proctoring event appears in admin live monitor.
10. **Coding question**: run sample cases (see pass/fail), submit → hidden-case score recorded.
11. Let the MCQ **section timer expire** → auto-submit + advance. Finish via **Submit and End Test** → success page.
12. **Evaluator**: open the candidate report → verify overall/section scores, timings, attempted/right/wrong, code history, proctoring timeline; override one score with a reason → check the **audit log** shows the override, the invitation sends, and the publish.
13. **Export** the report PDF and assessment CSV.
14. **Version freeze**: edit the published assessment → confirm a new version is created and the completed session still references the old version.

All 14 steps passing = the feature's acceptance scenarios for Modules 1–10 are demonstrably wired.

## Common issues

| Symptom | Fix |
| --- | --- |
| Judge0 submissions stuck `queued` | `docker compose logs judge0-workers`; ensure privileged mode / cgroup v2 flags per Judge0 CE docs |
| `prepared statement` errors | PgBouncer must run transaction pooling with asyncpg `statement_cache_size=0` (see research R12) |
| Emails not arriving | Unset RESEND_API_KEY → console transport; check `email_messages.status` |
| Camera check fails on `http://` | Browsers require secure context except `localhost` — use localhost, not LAN IP |
