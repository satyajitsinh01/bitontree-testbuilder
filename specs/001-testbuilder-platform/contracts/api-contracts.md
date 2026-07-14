# API Contracts: TestBuilder Platform

Base URL: `/api/v1`. All responses envelope: `{ "data": ..., "error": null }` or `{ "data": null, "error": { "code", "message", "details" } }`.
Auth: `Authorization: Bearer <access_jwt>`; refresh via httpOnly cookie. Admin endpoints require role(s) noted. All list endpoints support `?page,size,sort,q` and return `{items, total, page, size}`.
Errors: `401 unauthenticated`, `403 forbidden_role`, `404 not_found`, `409 conflict`, `422 validation_error`, `429 rate_limited`.

---

## 1. Auth

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/admin/login` | — | `{email, password}` → `{access_token, user, roles}` + refresh cookie |
| POST | `/auth/admin/refresh` | cookie | Rotate refresh, new access token; reuse detection → 401 + family revoked |
| POST | `/auth/admin/logout` | ✓ | Revoke refresh family |
| POST | `/auth/candidate/login` | — | `{username, password}` → `{access_token, assignment_summary}`; **403 window_not_started** ("Your test will start soon", `starts_at`), **403 window_expired**, **409 session_active** |
| POST | `/auth/candidate/refresh` | cookie | Same as admin; exp capped at window end |

## 2. Admin Users & Roles  (role: hr_admin)

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/admin/users` | List / create admin user `{email, full_name, roles[]}` |
| PATCH | `/admin/users/{id}` | Update name, active flag, roles |
| GET | `/admin/audit-logs` | Filter: `actor_id, entity_type, entity_id, action, from, to` (FR-007) |

## 3. Question Bank  (role: test_creator)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/questions` | Filter: `qtype, category, difficulty, status, tags, source, q` |
| POST | `/questions` | Create (body = question_version fields); runs quality checks (FR-047) |
| GET | `/questions/{id}` | Head + current version + versions list + quality flags |
| PUT | `/questions/{id}` | Edit → creates new question_version |
| POST | `/questions/{id}/status` | `{status: active|inactive|archived}`; AI drafts require approval first → 409 |
| POST | `/questions/{id}/approve` | Approve AI draft (FR-044); audit-logged |
| DELETE | `/questions/{id}` | Soft delete; blocked (409) if pinned in a frozen version |
| POST | `/questions/ai-generate` | `{prompt, qtype, count, difficulty, topic, skills[]}` → 202 `{generation_id}` (async) |
| GET | `/questions/ai-generations/{id}` | Status + resulting draft question ids |

## 4. Assessments & Test Builder  (role: test_creator)

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/assessments` | List / create `{title, description, settings}` |
| GET | `/assessments/{id}` | Head + current version with sections |
| PATCH | `/assessments/{id}` | Edit metadata/settings; **if current version frozen → auto-forks new draft version** (FR-034) |
| POST | `/assessments/{id}/sections` | Add section `{name, description, duration_min, weightage_pct, allowed_qtypes[], question_count, order_index}` |
| PATCH/DELETE | `/sections/{id}` | Edit/remove (same fork rule) |
| PUT | `/sections/{id}/questions` | Set picks + pool memberships `[{question_id, pool_group?, points}]` |
| PUT | `/sections/{id}/pool-rules` | `[{pool_group, select_count}]` (FR-046) |
| POST | `/assessments/{id}/publish` | Validates (FR-038: coverage, Σweightage=100, durations>0) → publishes version; 422 with per-check errors |
| GET | `/assessments/{id}/versions` | Version history with frozen flags |

## 5. Candidate Management  (role: hr_admin)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/assessments/{id}/assignments` | Candidates of this assessment: status, window, email status, score |
| POST | `/assessments/{id}/assignments` | Add one `{full_name, email, phone, window_start_at, window_end_at, send_email}`; **409 duplicate_email_in_assessment** (FR-013) |
| POST | `/assessments/{id}/assignments/import` | `{file_key}` (pre-uploaded) → 202 `{batch_id}` |
| GET | `/import-batches/{id}` | Progress + counts + `error_report_url` (FR-012) |
| GET | `/import-batches/template` | Download CSV/XLSX template |
| PATCH | `/assignments/{id}` | Edit fields / reschedule window (audit-logged) (FR-015) |
| DELETE | `/assignments/{id}` | Remove; expires credentials; confirm flag required if in_progress |
| POST | `/assignments/{id}/resend-invitation` | Resend (FR-091); also bulk: `POST /assessments/{id}/assignments/resend-invitations {ids[]}` |
| POST | `/assignments/{id}/sessions` | Admin recovery session (FR-024): `{window_start_at?, window_end_at?}` → terminates active session, resets/extends window; audit-logged |
| POST | `/uploads/presign` | `{purpose: import|evidence, content_type}` → `{url, key}` |

## 6. Candidate Exam  (candidate JWT, assignment-scoped)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/exam/summary` | Window, duration, rules, system requirements, restriction list (FR-051) |
| POST | `/exam/device-check` | `{camera, mic, network_mbps, browser, fullscreen}` → pass/fail per check (FR-050) |
| POST | `/exam/start` | Acknowledge rules → creates exam_session (or 409 session_active / 403 window); returns first section + session_questions (FR-052 order) |
| GET | `/exam/state` | Resume: current section, deadlines, `server_now`, question states, saved answers |
| GET | `/exam/sections/{id}/questions` | Questions of active section only (no answers/hidden data leaked) |
| PUT | `/exam/questions/{sqid}/answer` | Autosave `{payload}` → `{saved_at}` (FR-055); 409 if section not active |
| POST | `/exam/questions/{sqid}/checkpoint` | `{kind: next_question}` — records answer-of-record checkpoint (FR-035) |
| POST | `/exam/questions/{sqid}/mark-review` | Toggle marked_for_review |
| POST | `/exam/sections/{id}/submit` | Manual section submit → next section activated |
| POST | `/exam/submit` | "Submit and End Test" `{confirm: true}` → success payload (FR-057) |

Server enforces lazily on every call: window, section deadline, session status (R3).

## 7. Code Execution  (candidate JWT)

| Method | Path | Description |
| --- | --- | --- |
| POST | `/exam/questions/{sqid}/code/run` | `{language, source_code}` → 202 `{submission_id}`; visible cases only; 429 on rate limit (FR-067) |
| POST | `/exam/questions/{sqid}/code/submit` | Same, all cases; checkpoints answer with results + timing (FR-035) |
| GET | `/exam/code-submissions/{id}` | Poll status/results (WS push preferred); results respect `show_case_results` config |

Internal: `PUT /internal/judge0/callback` — Judge0 webhook, HMAC-verified.

## 8. Proctoring  (candidate JWT for ingest; admin for review)

| Method | Path | Description |
| --- | --- | --- |
| POST | `/exam/proctoring/events` | Batch client events `[{kind, occurred_at, detail}]` (WS preferred, REST fallback) |
| POST | `/exam/proctoring/evidence` | `{object_key, kind, captured_at}` after direct S3 upload (R8) |
| GET | `/sessions/{id}/proctoring/timeline` | (evaluator/hr_admin) events + evidence thumbnails, chronological (FR-075) |
| GET | `/sessions/{id}/proctoring/flags` | Warnings + red flags with AI confidence |

## 9. Evaluation & Reports  (role: evaluator; dashboards also hr_admin)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/assessments/{id}/results` | Candidate list: status, scores, flags, percentile (gated, FR-087) |
| GET | `/sessions/{id}/report` | Full candidate report (FR-084) |
| GET | `/sessions/{id}/answers` | Per-question answers, checkpoints, code history |
| PATCH | `/evaluations/{id}` | Override `{final_score, override_reason}` → audit-logged (FR-083) |
| POST | `/sessions/{id}/report/finalize` | Lock report after review |
| POST | `/sessions/{id}/report/export` | 202 → PDF generation; `GET /exports/{id}` → signed URL (FR-086) |
| POST | `/assessments/{id}/results/export` | CSV/Excel of all candidates |

## 10. Emails

| Method | Path | Description |
| --- | --- | --- |
| GET | `/assignments/{id}/emails` | Delivery history per candidate (FR-094) |
| POST | `/internal/resend/webhook` | Resend status webhook (signature-verified) |

---

## Cross-cutting

- **Rate limits**: `/auth/*` 10/min/IP; `/exam/*/answer` 60/min/session; code run/submit per FR-067.
- **Idempotency**: mutation endpoints on the exam path accept `Idempotency-Key` header (autosave retries).
- **Pagination** caps at `size=100`.
- **All timestamps** returned as ISO-8601 UTC with `server_now` included on exam-path responses.
