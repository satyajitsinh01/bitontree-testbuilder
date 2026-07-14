# Testing Strategy: TestBuilder Platform

**Input**: spec.md (FR-001…FR-094, NFR-001…008), data-model.md, contracts/
**Scope**: unit tests, functional (API/contract) tests, and feature (end-to-end) tests — per module and per feature.

---

## 1. Test Levels & Tooling

| Level | What it proves | Backend | Frontend |
| --- | --- | --- | --- |
| **Unit** | One function/service/component in isolation; all branches and edge cases | pytest + pytest-asyncio; factories via `factory_boy`; `time-machine` for IST clock control; `fakeredis` for lock/rate-limit logic | Jest + React Testing Library; `@testing-library/user-event`; MSW for API mocking |
| **Functional** | One API endpoint / WS channel behaves per contract: status codes, schemas, authz, side effects (DB rows, audit entries, queued jobs) | pytest + httpx `ASGITransport` client against the real app with a per-test transactional Postgres schema; ARQ jobs run inline (`burst` mode); Judge0/Gemini/Resend stubbed at the httpx layer | Jest integration tests of page-level components with MSW-simulated API |
| **Feature (E2E)** | A whole user story works through the real UI + API + DB + worker | Playwright (approved exception, see plan.md) driving the Next.js app against a compose stack (Postgres, Redis, MinIO, Judge0, stub Gemini/Resend) | same |

**Conventions**
- IDs: `UT-Mx-nn` (unit), `FT-Mx-nn` (functional), `FE-Mx-nn` (feature), where `Mx` = module 1–10.
- Every FR maps to ≥ 1 test ID (traceability table in §5).
- Coverage gates in CI: backend `services/` ≥ 85% branches; frontend `hooks/` + `components/exam/` ≥ 80%. Contract tests must cover **every** endpoint in api-contracts.md.
- Fixtures: `org`, `admin(role)`, `assessment(sections)`, `assignment(window)`, `active_session` — composable factories, no shared mutable seed data.
- Time: never `sleep`; all window/timer tests use `time-machine` to jump the IST clock.
- External stubs: `FakeJudge0` (deterministic per-case results), `FakeGemini` (canned JSON per capability), `FakeResend` (records sends, can simulate bounce webhook).

---

## 2. Module Test Matrices

### Module 1 — Admin, HR & Role Management

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M1-01 | auth service | Argon2id hash/verify roundtrip; wrong password fails; legacy-hash rejection |
| UT-M1-02 | JWT service | token exp ≤ 15 min; tampered signature rejected; expired token rejected |
| UT-M1-03 | refresh rotation | rotate returns new pair + revokes old; **reuse of rotated token revokes whole family** |
| UT-M1-04 | RBAC union | user with `evaluator`+`test_creator` gets union of permissions; empty roles → nothing |
| UT-M1-05 | audit writer | snapshot diff builds before/after correctly; write happens in caller's transaction (rollback ⇒ no audit row) |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M1-01 | POST /auth/admin/login | valid → 200 + access token + refresh cookie (httpOnly, Secure); bad creds → 401; 11th attempt/min → 429 |
| FT-M1-02 | POST /auth/admin/refresh | rotates; reused old cookie → 401 and family revoked in DB |
| FT-M1-03 | /admin/users | hr_admin can CRUD; evaluator-only token → 403; create with roles[] persists user_roles |
| FT-M1-04 | /admin/audit-logs | filters by actor/entity/action/date work; results immutable (no PATCH/DELETE route exists → 405) |
| FT-M1-05 | DB grants | raw `UPDATE audit_logs` under app role → permission denied (executed via SQL in test) |

**Feature**
- FE-M1-01: Admin logs in, creates a Test Creator user, logs out; new user logs in and sees only test-creation nav (FR-001/002).
- FE-M1-02: Admin changes an assessment timing → audit viewer shows the entry with before/after window (FR-005/006/007).

### Module 2 — Candidate Management (per-assessment)

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M2-01 | credentials service | username pattern `{code}-{seq}`; password ≥ 12 chars, charset policy; hash stored, plaintext returned once |
| UT-M2-02 | credential expiry | now > window_end ⇒ `credentials_expired`; removal ⇒ expired immediately |
| UT-M2-03 | import row validator | bad email / bad phone / end ≤ start / start in past / missing name → row-level errors with reasons |
| UT-M2-04 | in-file dedupe | duplicate email within file → first kept, rest rejected as `duplicate_in_file` |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M2-01 | POST assignments | valid → 201 + assignment + credentials; same email again → **409 duplicate_email_in_assessment** (case-insensitive: `A@x.com` vs `a@x.com`) |
| FT-M2-02 | same email, other assessment | → 201, independent credentials/timings (FR-014) |
| FT-M2-03 | import flow | presign → upload → 202 batch → poll: 500 rows (10 bad) ⇒ imported=490, failed=10, error report downloadable with row numbers + reasons |
| FT-M2-04 | PATCH /assignments/{id} | reschedule window → 200 + audit row; end ≤ start → 422 |
| FT-M2-05 | DELETE /assignments/{id} | in_progress without confirm flag → 409; with confirm → removed + credentials expired + session terminated |
| FT-M2-06 | send_email toggle | send_email=false ⇒ no email_messages row; later resend endpoint creates one |

**Feature**
- FE-M2-01: Import wizard — upload template with mixed rows, watch progress, download error report, see 490 candidates in table (FR-012).
- FE-M2-02: Add duplicate email via dialog → inline "already added to this test" error (FR-013).
- FE-M2-03: Reschedule + resend from row actions; email history shows new invitation (FR-015).

### Module 3 — Authentication, Invitation & Exam Access

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M3-01 | window gate | now < start → `window_not_started`; start ≤ now ≤ end → allow; now > end → `window_expired` (boundary: exactly-at-start allows, exactly-at-end expires) |
| UT-M3-02 | candidate JWT | `exp = min(now+15m, window_end)`; token scoped to assignment_id (claim check) |
| UT-M3-03 | session lock | acquire when free → ok; second acquire → refused; TTL lapse (missed heartbeats) → reclaimable |
| UT-M3-04 | invitation renderer | template contains link, credentials, IST window + local hint, duration, rules, system requirements (FR-020) |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M3-01 | POST /auth/candidate/login | before window → 403 `window_not_started` + `starts_at`; after → 403 `window_expired`; expired credentials → 401 |
| FT-M3-02 | concurrent login | active session exists → 409 `session_active`; DB partial unique index verified by racing two logins (both txns → exactly one wins) |
| FT-M3-03 | POST /assignments/{id}/sessions (admin recovery) | terminates old session (WS closed 4003), optionally widens window, audit-logged; candidate can log in again (FR-024) |
| FT-M3-04 | token expiry cap | jump clock past window_end → access AND refresh both rejected |

**Feature**
- FE-M3-01: Candidate opens link early → "Your test will start soon." with live countdown; clock jump (stub) past start → login proceeds (FR-022).
- FE-M3-02: Login on device A, then device B → B shows "assessment is active on another device" (FR-023).
- FE-M3-03: Admin resets session mid-exam → candidate A sees "session ended by administrator"; candidate resumes on new session with prior answers intact.

### Module 4 — Test Builder & Versioning

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M4-01 | publish validation | Σ weightage ≠ 100 → error; duration 0 → error; pool rule select_count > active members → error listing the section (FR-038) |
| UT-M4-02 | versioning service | edit on unfrozen draft mutates in place; edit after freeze forks version n+1; fork copies sections + pinned question_versions |
| UT-M4-03 | freeze guard | UPDATE on frozen version raises (trigger test) |
| UT-M4-04 | section ordering | reorder keeps unique (version, order_index); final section flag moves with reorder |
| UT-M4-05 | answer-of-record | checkpoint sequence autosave→next_question→run_code→submit_code ⇒ final = last checkpoint payload (FR-035) |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M4-01 | POST/PATCH sections | full CRUD; weightage/duration validation on publish, not on draft save |
| FT-M4-02 | POST /assessments/{id}/publish | happy path publishes version; broken invariants → 422 with per-check error list |
| FT-M4-03 | edit-after-start | start a session on v1, PATCH assessment → response indicates new version v2; session still pinned to v1; GET /versions shows both, v1 frozen (FR-034) |
| FT-M4-04 | section auto-submit | jump clock past section deadline → cron sweep marks section auto_submitted, next section activated; exam-call lazy check does same without sweep (FR-036) |
| FT-M4-05 | exam-end auto-submit | jump past `ends_at` → session auto_submitted, all current answers preserved (FR-037) |

**Feature**
- FE-M4-01 (Story: build & publish): create assessment, 3 sections with drag-reorder, attach questions + pool rule, publish → success toast; invalid weightage → inline section errors.
- FE-M4-02: With one candidate mid-test, edit a question count → banner "editing created version 2"; candidate's exam unchanged.

### Module 5 — Question Bank & AI Generation

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M5-01 | MCQ validation | < 2 options, or 0 correct ids, or correct id not in options → invalid_structure |
| UT-M5-02 | coding validation | reference solution failing own test cases (FakeJudge0) → `solution_fails_tests` flag |
| UT-M5-03 | duplicate check | trigram similarity ≥ 0.85 vs active bank → `duplicate` flag with matched id |
| UT-M5-04 | edit-as-version | edit creates version n+1; frozen-referenced version untouched |
| UT-M5-05 | pool selection | seeded RNG: same session id ⇒ identical selection/order across calls; distribution sanity over 1k sessions (each of 30 questions picked, no bias > tolerance) |
| UT-M5-06 | Gemini generation parser | valid structured JSON → draft questions with metadata; malformed/partial JSON → generation `failed`, no rows created |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M5-01 | POST /questions | creates active (manual) with quality checks run; structural failure → 422 |
| FT-M5-02 | POST /questions/ai-generate | 202 + generation id; poll → draft questions exist with source=`ai`, stored prompt/model (FR-042/045) |
| FT-M5-03 | draft gating | attach a draft AI question to a section → 409; approve → attach succeeds (FR-043/044) |
| FT-M5-04 | approve | records approver, audit row; reject → question archived |
| FT-M5-05 | status/delete | deactivate hides from picker; DELETE pinned-in-frozen-version → 409 |

**Feature**
- FE-M5-01 (Story 3): prompt AI for 30 MCQs → review queue shows drafts with quality flags → edit one, approve 25, reject rest → configure "pick 10 of 25" pool → two different candidates receive different 10-question sets, each stable across refresh (FR-046/052).

### Module 6 — Candidate Test Experience

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M6-01 | `useAutosave` hook | debounces 2 s; flush on blur/navigation; offline → queues mutation, replays with idempotency key on reconnect; no data older than 3 s unflushed (NFR-002) |
| UT-M6-02 | `useServerTimer` | renders from server deadline + drift offset; resync on `session.state`; never trusts local clock alone |
| UT-M6-03 | progress palette | state transitions unseen→seen→answered / marked_review; counts match (FR-054) |
| UT-M6-04 | device-check components | each check (camera, mic, network, browser, fullscreen) gates independently; Start disabled until all required pass (FR-050) |
| UT-M6-05 | option shuffle render | renders per persisted `option_order`; answer maps to option id, not index |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M6-01 | POST /exam/start | requires rules acknowledgment flag; creates session_questions with randomized order + option_order persisted; second start → 409 |
| FT-M6-02 | PUT answer (autosave) | upsert + `saved_at`; answer to inactive/expired section → 409; idempotency key dedupes retries |
| FT-M6-03 | GET /exam/state | resume returns saved answers, question states, deadlines, `server_now` — after simulated disconnect, state is complete |
| FT-M6-04 | mark-review / navigation | toggles persist; next_question checkpoint appended (FR-035/053) |
| FT-M6-05 | POST /exam/submit | requires `confirm:true`; success payload; any exam call after → 401/409; success page data (FR-057) |
| FT-M6-06 | data leakage guard | exam question payloads never include correct_option_ids, hidden test cases, or rubric (snapshot-tested schema) |

**Feature**
- FE-M6-01 (Story 2, core): full exam run — device check, rules acknowledgment, answer MCQs with skip/revisit/mark, watch palette counts, refresh mid-section (answers persist), section timeout auto-advances, final "Submit and End Test" → success page.
- FE-M6-02: Kill network for 10 s while typing → banner "reconnecting", answers replay on reconnect, nothing lost beyond 3 s.

### Module 7 — Coding / DSA Engine

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M7-01 | Judge0 client mapping | language → judge0 id for JS/Python/Java/C++/C; unknown language → validation error |
| UT-M7-02 | result mapper | judge0 statuses → compile_error / runtime_error / timeout / completed; stdout/stderr truncated to limit |
| UT-M7-03 | scorer | weighted per-case: 3/5 cases (weights 2,2,1,1,1) passing {2,2,1} → 5/7 of max points; all fail → 0; partial credit off → all-or-nothing |
| UT-M7-04 | rate limiter | 10 runs/min allowed, 11th → limited; window slides; submit cap 30/question enforced |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M7-01 | POST code/run | 202 → callback → results contain **only visible cases**; compile error surfaced with message |
| FT-M7-02 | POST code/submit | all cases evaluated; hidden case outputs masked per `show_case_results` config (all / visible_only / count_only) |
| FT-M7-03 | persistence | every run/submit row stores language, source, per-case results, time, memory, score (FR-066) |
| FT-M7-04 | rate limit | burst 11 runs → 429 with retry-after; other candidates unaffected |
| FT-M7-05 | checkpoint link | submit creates `submit_code` checkpoint referencing the submission; final answer = last submit (FR-035) |
| FT-M7-06 | callback security | Judge0 callback with bad HMAC → 401, submission untouched |

**Feature**
- FE-M7-01: Open coding question → switch language (starter code swaps) → Run (see 2/3 visible cases pass, stderr for the failure) → fix → Submit → score recorded; submission history visible to evaluator later.
- FE-M7-02: Section expires while a run is in flight → run result still recorded; section auto-submitted with last submitted code as final.

### Module 8 — Proctoring & Integrity

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M8-01 | ProctorGuard hooks | visibilitychange → tab_switch event; blur → window_blur; fullscreenchange exit → fullscreen_exit + re-entry prompt; copy/paste → intercepted + event |
| UT-M8-02 | capture loop | fires at configured interval; upload failure → retry then `capture_failed` event (never silent) (FR-072) |
| UT-M8-03 | severity mapper | policy strict/standard/lenient maps event kinds → block/warn/log (FR-076) |
| UT-M8-04 | AI analysis parser | FakeGemini "two faces" response → `multiple_faces` red_flag with confidence; low-confidence → warning not red_flag |
| UT-M8-05 | event timestamp bounding | client `occurred_at` in future/past beyond skew tolerance → clamped to `received_at` |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M8-01 | POST proctoring/events (batch) | events persisted with received_at; invalid kind → 422; WS path produces identical rows |
| FT-M8-02 | evidence flow | presign → register object_key → evidence row; AI job samples and writes analysis (FR-073/074) |
| FT-M8-03 | GET timeline | evaluator sees chronological events + evidence thumbs; candidate token → 403 (FR-075) |
| FT-M8-04 | retention purge | jump clock past retention days → cron deletes evidence rows + storage objects; events remain (NFR-006) |

**Feature**
- FE-M8-01: During exam, switch tab twice and exit fullscreen → on-screen warnings; admin live monitor shows the flags in real time; timeline shows all three with timestamps.
- FE-M8-02: Deny camera mid-exam under `standard` policy → warning + event; under `strict` policy → exam blocked until restored.

### Module 9 — Evaluation, AI Review & Reports

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M9-01 | MCQ scorer | single correct; multi-correct (exact-set match); negative marking on/off; unanswered → 0, not negative |
| UT-M9-02 | section aggregation | weightage math: section scores × weightage = overall; durations summed from session_sections |
| UT-M9-03 | attempted/right/wrong counts | derived correctly incl. marked-review answered questions |
| UT-M9-04 | percentile gate | cohort 19 → percentile/rank null; cohort 20 → computed; ties share rank (FR-087) |
| UT-M9-05 | AI written eval parser | FakeGemini rubric response → score+rationale+confidence; confidence < threshold → review queue flag |
| UT-M9-06 | override rule | override without reason → rejected; with reason → final_score replaced, audit row in same txn (FR-083) |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M9-01 | submit → auto-eval | completing a session triggers evaluation: MCQ + coding scored, text queued for AI; report `pending_review` |
| FT-M9-02 | PATCH /evaluations/{id} | evaluator overrides → report recomputed; hr_admin without evaluator role → 403 |
| FT-M9-03 | GET /sessions/{id}/report | full payload per FR-084 (scores, durations, breakdown, code history, proctor timeline, AI observations labeled, flags) |
| FT-M9-04 | exports | PDF job → artifact in storage + signed URL; CSV columns match candidate list incl. statuses/scores |
| FT-M9-05 | finalize | after finalize, further overrides → 409 |

**Feature**
- FE-M9-01 (Story 4): evaluator dashboard → open candidate → accept AI score on Q1, override Q2 with reason → finalize → report shows final scores; audit log has the override; export PDF downloads.
- FE-M9-02: Results table for 25 completed candidates shows percentile/rank; for a 5-candidate assessment the columns are absent (FR-087).

### Module 10 — Notifications & Email

**Unit**
| ID | Target | Case → Expected |
| --- | --- | --- |
| UT-M10-01 | reminder bucketing | assignments at start−24h±window and start−1h±window selected once; completed/removed skipped; reschedule re-buckets naturally (FR-093) |
| UT-M10-02 | template rendering | all variables filled; missing variable → render error (fail fast, not blank email) |
| UT-M10-03 | webhook mapper | Resend delivered/bounced/complained → status transitions; unknown message id → logged, 200 (idempotent) |

**Functional**
| ID | Endpoint | Case → Expected |
| --- | --- | --- |
| FT-M10-01 | invitation on create | send_email=true → email_messages row `queued`→`sent` (FakeResend); toggle off → none (FR-092) |
| FT-M10-02 | resend single/bulk | creates `resend`-kind messages; each send audit-logged (FR-091) |
| FT-M10-03 | webhook | signed bounce webhook → status `bounced`, visible in GET /assignments/{id}/emails; bad signature → 401 (FR-094) |

**Feature**
- FE-M10-01: Candidate row shows email status chip (sent/bounced); fix a bounced email address → resend → chip updates to sent.

---

## 3. Cross-Cutting Test Suites

| Suite | Content |
| --- | --- |
| **Security (maps NFR-005)** | authz matrix test: every endpoint × every role (incl. candidate token on admin routes and vice versa) asserted from a table — new endpoints fail the matrix until classified; IDOR probes (candidate A's token on candidate B's session/answers/report → 403/404); rate-limit suite for auth + exam paths; signed-URL TTL expiry |
| **Timezone/clock** | parametrized suite running window/timer cases at IST-midnight boundaries, DST-less IST vs UTC conversion, and client clocks skewed ±12 h |
| **Concurrency** | racing tests: double login, double start, double submit, simultaneous autosaves to one answer (last-write-wins with idempotency), parallel imports to same assessment with overlapping emails |
| **WS contract** | connect/auth, heartbeat lock refresh, supersede (4001), state replay on reconnect, `section.expired` push on sweep |
| **Load (NFR-001/004)** | k6 or locust scripts: 1k concurrent answer-saves p95 < 300 ms; 200 concurrent code submissions queue-depth report — run nightly, not per-PR |

## 4. Where Tests Live & Run

```
backend/tests/
├── unit/            # UT-* (services, scorers, validators, mappers)
├── contract/        # FT-* endpoint schema/status tests (one file per contract §)
├── integration/     # FT-* multi-step + cross-cutting suites (per user story)
└── conftest.py      # factories, FakeJudge0/FakeGemini/FakeResend, time-machine, txn DB

frontend/
├── src/**/__tests__/  # UT-* component/hook tests (Jest + RTL, MSW)
└── e2e/               # FE-* Playwright specs, tagged @module-N and @story-N
```

CI stages: (1) lint+types → (2) BE unit+contract & FE Jest in parallel → (3) BE integration (compose services) → (4) Playwright FE-* on merge to main + nightly → (5) nightly load suite. A PR merges only with stages 1–3 green; stage 4 failures block release, not merge.

## 5. FR → Test Traceability (summary)

| FRs | Covered by |
| --- | --- |
| FR-001–007 | UT-M1-01…05, FT-M1-01…05, FE-M1-01/02 |
| FR-010–018 | UT-M2-01…04, FT-M2-01…06, FE-M2-01…03 |
| FR-020–026 | UT-M3-01…04, FT-M3-01…04, FE-M3-01…03 |
| FR-030–038 | UT-M4-01…05, FT-M4-01…05, FE-M4-01/02 |
| FR-040–047 | UT-M5-01…06, FT-M5-01…05, FE-M5-01 |
| FR-050–057 | UT-M6-01…05, FT-M6-01…06, FE-M6-01/02 |
| FR-060–067 | UT-M7-01…04, FT-M7-01…06, FE-M7-01/02 |
| FR-070–076 | UT-M8-01…05, FT-M8-01…04, FE-M8-01/02 |
| FR-080–088 | UT-M9-01…06, FT-M9-01…05, FE-M9-01/02 |
| FR-090–094 | UT-M10-01…03, FT-M10-01…03, FE-M10-01 |
| NFR-001/002/004 | load suite + UT-M6-01 |
| NFR-005 | security suite |
| NFR-006 | FT-M8-04 |

Rule: any new FR added to spec.md must land with at least one row here — enforced in PR review checklist.
