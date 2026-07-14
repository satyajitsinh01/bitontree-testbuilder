# Feature Specification: TestBuilder — Online Assessment Platform

**Feature Branch**: `001-testbuilder-platform`
**Created**: 2026-07-14
**Status**: Draft
**Input**: Full product requirements for an admin-driven candidate assessment platform with test builder, question bank + AI generation, coding engine, proctoring, evaluation/reports, and email notifications.

---

## Execution Flow (main)

```
1. Admin (HR) signs in → manages organization, users, question bank, assessments
2. Test Creator builds an assessment: ordered sections → question rules/pools → publish
3. Admin adds candidates to an assessment (manual or CSV/Excel bulk) → invitations sent
4. Candidate logs in with per-assignment temporary credentials inside the window
5. Device check → full-screen exam → sectioned, timed test with autosave + proctoring
6. Coding questions execute in sandboxed runner; every run/submission recorded
7. On submission/timeout: auto-evaluation (MCQ, code), AI-assisted text review
8. Evaluator reviews AI suggestions, finalizes scores → reports generated
9. Admin views dashboards, drills into candidate detail, exports reports
```

---

## ⚡ Quick Guidelines

- ✅ Candidates exist only inside assessments (via `test_assignment`) — no global student module.
- ✅ Server IST time governs all windows, timers, and credential expiry.
- ✅ Every admin is equally powerful within their role permissions; there is no super-admin hierarchy beyond roles.
- ❌ No public self-registration for candidates; access is invitation-only.

---

## User Personas

| Persona                | Description                                                        |
| ---------------------- | ------------------------------------------------------------------ |
| **HR/Admin**           | Manages org, users, candidates, invitations, schedules, reports    |
| **Test Creator**       | Builds assessments, sections, question bank, AI question workflows |
| **Evaluator/Reviewer** | Reviews AI-scored answers, proctoring flags, finalizes scores      |
| **Candidate**          | Invited test taker with per-assignment temporary credentials       |

A single user account may hold multiple roles. All admin-side roles authenticate through the same admin login; candidates authenticate through a separate candidate login flow.

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story 1 — HR runs a hiring assessment end-to-end
An HR admin creates a "Backend Engineer Screening" assessment, imports 200 candidates from Excel with individual start/end windows, sends invitations, monitors live progress, and exports a ranked report after the window closes.

### Primary User Story 2 — Candidate takes a proctored test
A candidate opens the invitation link, logs in with temporary credentials, passes the device check (camera, mic, network, browser, full-screen), and takes a 3-section test (Aptitude MCQ → Written → DSA coding). Answers autosave; each section auto-submits on timeout; the final section ends with "Submit and End Test".

### Primary User Story 3 — Test Creator uses AI to build a question pool
A test creator prompts the AI to generate 30 medium-difficulty Python MCQs, reviews/edits the drafts, approves 25, and configures a section rule "randomly select 10 of these 25" to reduce cheating.

### Primary User Story 4 — Evaluator finalizes results
An evaluator opens a candidate report, sees MCQ/code auto-scores, reviews AI-suggested scores for written answers, adjusts one score (audit-logged), reviews the proctoring timeline with screenshots and red flags, and publishes the final report.

### Acceptance Scenarios

#### Module 1 — Admin, HR & Role Management
1. **Given** a user with role HR/Admin, **When** they sign in, **Then** they can access org, user, test, candidate, and report management; a user with only Evaluator role cannot access test creation.
2. **Given** any admin performs a test edit, timing change, invitation send, manual score change, or session reset, **When** the action commits, **Then** an immutable audit record exists with actor, before/after, and IST timestamp.
3. **Given** an attempt to modify or delete an audit record via any API, **Then** the operation is rejected (no endpoint exists; DB role lacks the grant).
4. **Given** two HR/Admin users, **Then** both have identical capabilities (every admin equally powerful within a role — no owner/super-admin tier).

#### Module 2 — Candidate Management (per-assessment)
1. **Given** an assessment, **When** admin adds a candidate manually with name, email, phone, and start/end datetimes, **Then** a `test_assignment` links the candidate to that assessment with those timings.
2. **Given** a CSV/Excel of 500 rows, **When** admin bulk-imports into an assessment, **Then** valid rows create assignments, invalid rows are returned in a per-row error report (row number + reason), and nothing partial-commits within a row.
3. **Given** an email already assigned to this assessment, **When** the same email is imported/added again, **Then** the row is rejected with "duplicate email in this assessment".
4. **Given** a candidate email that exists in a *different* assessment, **When** added here, **Then** a new independent assignment is created with its own credentials, timings, attempts, and report.
5. **Given** an assignment, **When** admin edits timings, removes, reschedules, or resends the invitation, **Then** the change applies and is audit-logged; removal of an in-progress candidate requires explicit confirmation.
6. **Given** an assignment is created, **Then** temporary credentials unique to that assignment are generated; **When** the candidate's assessment end time passes, **Then** the credentials no longer authenticate.
7. **Given** the import/assignment flow, **When** admin toggles "send invitation email" off, **Then** assignments are created without emails; admin can send later.

#### Module 3 — Authentication, Invitation & Exam Access
1. **Given** a valid invitation, **Then** it contains the assessment link, login credentials, assessment window, duration, rules, and system requirements.
2. **Given** a candidate logs in before their window opens (server IST), **Then** they see "Your test will start soon." with a countdown; the test does not unlock.
3. **Given** a candidate logs in after the window closes, **Then** they see "Assessment window has expired." and cannot start.
4. **Given** a candidate has an active session, **When** the same credentials log in from another device/tab, **Then** the new login is refused (or, per config, the old session is terminated) — never two concurrent active sessions.
5. **Given** a candidate hit a technical problem, **When** an admin creates a new session for that assignment and adjusts timings, **Then** the candidate can log in again under the new window; the action is audit-logged.
6. **Given** any authenticated call, **Then** access tokens are short-lived JWTs and refresh tokens are stored securely (httpOnly cookie) and rotated on use.

#### Module 4 — Test Builder
1. **Given** a Test Creator, **When** they create an assessment, **Then** they can add ordered sections each with name, description, duration, weightage, allowed question types, and question count.
2. **Given** a section, **Then** the candidate can navigate freely among that section's questions but cannot re-enter a submitted/expired section.
3. **Given** the final section, **Then** it ends with a "Submit and End Test" action.
4. **Given** at least one candidate has started the assessment, **When** any edit is made, **Then** a new version is created; started candidates continue on their frozen version.
5. **Given** a section timer reaches zero, **Then** the server auto-submits the section's current answers and moves the candidate to the next section.
6. **Given** the overall assessment end time (or total duration) is reached, **Then** the server auto-submits everything in its current state.
7. **Given** a candidate answering, **Then** the answer of record for each question is the latest state captured at checkpoints: pressing next question (current answer), run code, and submit code (with timing and test-case results); the latest version counts as final.

#### Module 5 — Question Bank & AI Generation
1. **Given** the question bank, **Then** every question has type, category, answer type, and difficulty; admins can create, edit, delete, activate/deactivate, tag, and reuse questions across assessments.
2. **Given** an AI prompt, **When** generation completes, **Then** all generated questions have status `draft` and are excluded from assessment selection until approved.
3. **Given** a draft AI question, **When** admin edits and approves it, **Then** it becomes `active` and its metadata records source = `ai`, model, prompt, and approver.
4. **Given** any question, **Then** metadata includes topic, difficulty, skills, expected duration, language, source, creator, and version.
5. **Given** a section configured with pool rule "randomly select 10 of 30", **When** each candidate starts, **Then** they receive an independent random selection of 10, persisted for reproducibility.
6. **Given** question creation or import, **Then** quality checks flag duplicates (similarity), ambiguity, bias, and invalid structure (e.g., MCQ with no correct option) before activation.

#### Module 6 — Candidate Test Experience
1. **Given** the pre-test page, **Then** camera, microphone, internet connectivity, browser compatibility, and full-screen capability are each verified; the Start button enables only when all pass; all restrictions (full-screen, tab-switch, copy/paste) are explained before starting.
2. **Given** a section, **Then** question order is randomized per candidate and MCQ options are randomized per candidate (persisted so revisits show the same order).
3. **Given** an in-section question list, **Then** candidates can skip, revisit, and mark for review; the UI shows section timer and counts of attempted / unattempted / marked-for-review.
4. **Given** any answer input, **Then** it autosaves (debounced) and survives refresh/crash within the session.
5. **Given** final submission, **Then** a success page confirms completion and the session ends.

#### Module 7 — Coding / DSA Engine
1. **Given** a coding question, **Then** the candidate gets a code editor with language selection among JavaScript, Python, Java, C++ (and C where enabled).
2. **Given** "Run Code", **Then** the code executes against sample/public test cases in an isolated sandbox and shows compile errors, runtime errors, stdout, and pass/fail per visible case as configured.
3. **Given** "Submit Code", **Then** hidden test cases evaluate the submission; the score is test-case based (weighted per case); results visibility follows question config.
4. **Given** every run/submission, **Then** the system stores language, code, execution result, per-case outcomes, execution time, memory, and score.
5. **Given** burst traffic, **Then** executions are queued with rate limits per candidate (e.g., max N runs/min) and fair scheduling; the sandbox has CPU, memory, and wall-time limits and no network access.

#### Module 8 — Proctoring & Integrity
1. **Given** exam start, **Then** camera + microphone permission and full-screen are required; losing either raises an event and an on-screen warning.
2. **Given** the exam, **Then** tab switches, window blur, fullscreen exits, copy/paste attempts, and permission losses each create timestamped proctoring events.
3. **Given** a configured interval (default 5 s), **Then** webcam screenshots are captured and stored as evidence in object storage.
4. **Given** collected evidence, **Then** AI analysis flags suspicious patterns (multiple faces, absent candidate, gaze anomalies, repeated tab-switching) as warnings/red flags.
5. **Given** an admin/evaluator, **Then** they can view per-candidate warnings, red flags, and a chronological activity timeline with linked evidence.

#### Module 9 — Evaluation, AI Review & Reports
1. **Given** submission, **Then** MCQs are exact-scored and coding questions test-case-scored automatically; written answers get AI-suggested scores with rationale.
2. **Given** an evaluator, **When** they override an AI-suggested or manual score, **Then** the override + reason is audit-logged and the report reflects the final human score.
3. **Given** a candidate report, **Then** it includes overall score, per-section scores with time spent, attempted/unattempted/right/wrong counts, full coding submission history, proctoring timeline, AI observations, and red flags.
4. **Given** the admin dashboard, **Then** admins can click through from assessment → candidate list → candidate detail; reports export as PDF/CSV.
5. **Given** a cohort of completed candidates, **Then** percentile/rank shows only when cohort size ≥ 20 (configurable threshold).

#### Module 10 — Notifications & Email
1. **Given** an assignment with email enabled, **Then** the invitation email includes credentials/login instructions, schedule with timezone, link, and rules.
2. **Given** the admin panel, **Then** invitations can be resent per candidate or in bulk; each send is logged.
3. **Given** reminder configuration, **Then** reminder emails go out before test start (e.g., 24 h and 1 h prior) to candidates who haven't completed.
4. **Given** email sends, **Then** delivery status (queued/sent/failed) is tracked and visible per candidate.

### Edge Cases

- **Clock skew / timezone**: candidate device clock is wrong → all gating uses server IST; UI shows both IST and local time.
- **Network drop mid-exam**: answers autosaved server-side; on reconnect within the window and same session token, the candidate resumes exactly where they left off; timers continue running server-side during disconnection.
- **Browser crash / accidental close**: same-session resume allowed; a second concurrent login is still blocked.
- **Section timeout during code execution**: the in-flight execution completes and is recorded; the section still auto-submits with the last submitted/checkpointed code as final.
- **Bulk import**: duplicate emails inside the file (keep first, reject rest), invalid email/phone formats, end time before start time, start time in the past — all rejected per-row with reasons.
- **Assessment edited while candidates mid-test**: new version created; in-flight candidates unaffected; new starters get the new version.
- **Candidate finishes early**: explicit "Submit and End Test" requires confirmation; after submission no re-entry.
- **Judge0/runner outage**: runs/submissions queue with retry + backoff; candidate sees "execution queued"; section timing is not paused (documented rule) but admin may grant a new session.
- **Screenshot upload failure**: retried in background; a `capture_failed` proctoring event is logged rather than silently dropped.
- **Email bounce**: assignment shows `failed` delivery status; admin can correct email and resend (audit-logged edit).
- **Same candidate in two overlapping assessments**: allowed — separate credentials and sessions; the one-active-session rule applies per assignment.
- **Empty question pool after rules applied**: publishing is blocked with a validation error ("rule requires 10, only 6 active questions match").
- **Candidate denies camera mid-test**: event logged, prominent warning, configurable policy (warn-only vs. block until restored).

---

## Requirements *(mandatory)*

### Module 1 — Admin, HR & Role Management

- **FR-001**: System MUST provide admin authentication (email + password, Argon2id-hashed) separate from candidate authentication.
- **FR-002**: System MUST implement role-based access control with roles: `hr_admin`, `test_creator`, `evaluator`. A user may hold multiple roles; permissions are the union of role permissions.
- **FR-003**: All admins with the same role set MUST have identical capabilities (no hidden super-admin tier).
- **FR-004**: System MUST support managing organizations, admin users, assessments, candidates (within assessments), and reports via the admin panel.
- **FR-005**: System MUST write an append-only audit log entry for: assessment create/edit/publish/version, timing changes, invitation sends/resends, manual score changes, session resets, question approve/deactivate, candidate add/edit/remove.
- **FR-006**: Audit log entries MUST be immutable: no update/delete API, no update/delete DB grant for the application role; entries store actor id, action, entity type/id, before/after JSON snapshots, server IST timestamp, request id, and source IP.
- **FR-007**: Admin panel MUST provide a filterable audit log viewer (by actor, entity, action, date range).

### Module 2 — Candidate Management (per-assessment)

- **FR-010**: Candidates MUST be managed inside a specific assessment via `test_assignment`; there is no standalone global student module.
- **FR-011**: Admin MUST be able to add a candidate manually with fields: name, email, phone, assessment start datetime, assessment end datetime.
- **FR-012**: Admin MUST be able to bulk-import candidates from CSV/Excel into a specific assessment, with a downloadable template, per-row validation, and a per-row error report; valid rows import even when other rows fail.
- **FR-013**: System MUST reject adding the same email twice to the same assessment (case-insensitive), both in manual add and bulk import (including duplicates within one file).
- **FR-014**: The same email MAY exist across different assessments; each assignment has independent credentials, timings, attempts, sessions, and reports.
- **FR-015**: Admin MUST be able to view, edit, remove, reschedule, and resend invitations for candidates of an assessment; each action is audit-logged.
- **FR-016**: System MUST generate temporary login credentials per assignment (system-generated username + strong random password, shown once / delivered by email).
- **FR-017**: Credentials MUST stop authenticating once the candidate's assessment end time (server IST) passes, and immediately upon assignment removal.
- **FR-018**: Invitation email sending MUST be optional (toggle) at import/assignment time and re-triggerable later.

### Module 3 — Authentication, Invitation & Exam Access

- **FR-020**: Invitation MUST contain: assessment link, login credentials, assessment window (IST + candidate-local hint), duration, rules, and system requirements.
- **FR-021**: Test access MUST unlock only inside the assignment's window evaluated against server IST time.
- **FR-022**: Before the window: show "Your test will start soon." with countdown. After the window: show "Assessment window has expired."
- **FR-023**: System MUST enforce exactly one active exam session per assignment using a DB session record plus a Redis lock; concurrent login attempts are rejected with a clear message.
- **FR-024**: Admin MUST be able to create a new session for any assignment (e.g., after a technical failure) and adjust that candidate's timings; prior session is terminated; action audit-logged.
- **FR-025**: Auth MUST use short-lived JWT access tokens (≤ 15 min) with rotating refresh tokens stored in httpOnly, Secure, SameSite cookies; refresh reuse detection revokes the token family.
- **FR-026**: Candidate tokens MUST be scoped to the specific assignment and expire no later than the assessment end time.

### Module 4 — Test Builder

- **FR-030**: Admin/Test Creator MUST be able to create assessments composed of ordered sections.
- **FR-031**: Each section MUST define: name, description, duration (minutes), weightage (% of total), allowed question types, question count, and navigation mode (free navigation within section).
- **FR-032**: Supported section archetypes include Aptitude, English, MCQ, DSA/Coding, Written Answers (archetype = label + default config, not a hard type).
- **FR-033**: The final section MUST end with a "Submit and End Test" action requiring confirmation.
- **FR-034**: When the first candidate starts an assessment, the assessment version MUST freeze; any later edit MUST create a new version. In-flight candidates stay on their frozen version.
- **FR-035**: Answer-of-record checkpoints: pressing next question saves the current answer; "run code" and "submit code" checkpoint code answers with timing and test-case results; the latest checkpointed state is the final answer.
- **FR-036**: On section timeout, server MUST auto-submit the section's current answers and advance the candidate.
- **FR-037**: At overall exam end time, server MUST auto-submit the entire current state and close the session.
- **FR-038**: Publishing MUST validate: every section has enough active questions for its rules, weightages sum to 100%, durations > 0.

### Module 5 — Question Bank & AI Generation

- **FR-040**: System MUST provide a central question bank; each question has question type (`mcq` | `text` | `coding`), category, answer type, and difficulty (`easy` | `medium` | `hard`).
- **FR-041**: Admin MUST be able to create, edit (creates a new question version), soft-delete, activate/deactivate, tag, and reuse questions across assessments.
- **FR-042**: System MUST generate questions from admin prompts via AI for types: MCQ, text/written, and DSA/coding (including starter code + test cases for coding).
- **FR-043**: AI-generated questions MUST default to status `draft` and MUST NOT be selectable in assessments until a human approves them.
- **FR-044**: Admin MUST be able to review, edit, approve, or reject AI drafts; approval records the approver and is audit-logged.
- **FR-045**: Every question MUST store metadata: topic, difficulty, skills[], expected duration, language, source (`manual` | `ai` | `import`), creator, version.
- **FR-046**: Sections MUST support question pools with selection rules (e.g., "randomly select 10 of 30"); per-candidate selection is random, seeded, and persisted.
- **FR-047**: System MUST run quality checks flagging: near-duplicates (text similarity), ambiguity heuristics, bias/inappropriate content (AI check), and structural invalidity (e.g., MCQ without exactly-defined correct option(s), coding question whose reference solution fails its own test cases).

### Module 6 — Candidate Test Experience

- **FR-050**: Pre-test device check MUST verify camera, microphone, internet connection quality, browser compatibility, and full-screen capability; Start enables only after all required checks pass.
- **FR-051**: All exam restrictions (full-screen requirement, tab-switch detection, copy/paste blocking, camera monitoring) MUST be clearly explained before the exam begins and acknowledged by the candidate.
- **FR-052**: Question order MUST be randomized per candidate; MCQ option order MUST be randomized per candidate; both persisted so the layout is stable across revisits/reconnects.
- **FR-053**: Within an active section, candidates MUST be able to skip, revisit, and mark questions for review.
- **FR-054**: UI MUST show the section timer (server-synced) and live progress: attempted, unattempted, marked-for-review.
- **FR-055**: All answers MUST auto-save (debounced ≤ 3 s after change and on navigation) with optimistic UI + server acknowledgment.
- **FR-056**: On section expiry, current answers auto-submit (FR-036); the candidate is informed and moved forward.
- **FR-057**: After final submission, a success page confirms receipt; the session is terminated and re-entry blocked.

### Module 7 — Coding / DSA Engine

- **FR-060**: Coding questions MUST support JavaScript, Python, Java, and C++ (C optional per deployment); the question may restrict allowed languages.
- **FR-061**: Editor MUST provide language selection, syntax highlighting, and per-language starter code (Monaco).
- **FR-062**: Sample/public test cases MUST be visible and runnable by the candidate; hidden test cases are used only for evaluation.
- **FR-063**: Execution MUST occur in isolated sandboxes (Docker / Judge0 CE) with CPU, memory, and wall-time limits and no network access.
- **FR-064**: System MUST show compile errors, runtime errors, and per-visible-case pass/fail as configured on the question.
- **FR-065**: Scoring MUST be test-case based with per-case weights; partial credit supported.
- **FR-066**: Every run and submission MUST persist: language, full source code, execution status, per-case results, stdout/stderr (truncated), execution time, memory, and computed score.
- **FR-067**: Executions MUST pass through a Redis-backed job queue with per-candidate rate limits (default: 10 runs/min, 30 submissions/exam/question — configurable) and global concurrency control.

### Module 8 — Proctoring & Integrity Monitoring

- **FR-070**: Exam start MUST require granted camera + microphone permissions and full-screen mode.
- **FR-071**: The following MUST create timestamped proctoring events: tab switch, window blur, fullscreen exit, copy attempt, paste attempt, camera/mic permission loss, devtools open (best-effort), multiple-display detection (best-effort).
- **FR-072**: Webcam screenshots MUST be captured periodically (default every 5 s, configurable per assessment) and uploaded to object storage with retry; failures log a `capture_failed` event.
- **FR-073**: All proctoring events and evidence MUST be stored and linked to the exam session with server-received timestamps.
- **FR-074**: AI MUST analyze evidence (async) for suspicious behavior — multiple faces, no face, gaze away patterns, phone-like objects — producing warnings and red flags with confidence scores.
- **FR-075**: Admin/Evaluator MUST see per-candidate warnings, red flags, and a chronological activity timeline with evidence thumbnails and event details.
- **FR-076**: Proctoring policy per assessment MUST be configurable: strict (block on violation), standard (warn + log), lenient (log only).

### Module 9 — Evaluation, AI Review & Reports

- **FR-080**: MCQ answers MUST be auto-scored exactly (single/multiple correct supported, with negative marking configurable).
- **FR-081**: Coding answers MUST be auto-scored from hidden test-case results (FR-065) using the final checkpointed submission.
- **FR-082**: Written answers MUST receive AI-assisted evaluation producing a suggested score + rationale against the question's rubric/expected answer.
- **FR-083**: Evaluators MUST be able to accept or override any AI-suggested or auto score; overrides require a reason and are audit-logged.
- **FR-084**: Candidate report MUST include: overall score, per-section scores with duration spent, attempted/unattempted/right/wrong breakdown, coding submission history, proctoring event timeline, AI-generated observations, and red flags/warnings.
- **FR-085**: Admin dashboard MUST support click-through: assessments list → assessment detail (candidate list with statuses/scores) → candidate report.
- **FR-086**: Reports MUST be exportable: candidate report as PDF, assessment results as CSV/Excel.
- **FR-087**: Percentile/rank MUST be displayed only when the completed cohort for that assessment ≥ 20 (configurable threshold).
- **FR-088**: An AI summary of overall candidate performance (strengths/weaknesses per skill) MUST be generated for each completed candidate and marked as AI-generated.

### Module 10 — Notifications & Email

- **FR-090**: System MUST send transactional emails via Resend: invitation (credentials, schedule + timezone, link, rules, system requirements), reminders, and admin-triggered resends.
- **FR-091**: Invitation resend MUST be available per candidate and in bulk from the admin panel.
- **FR-092**: Email sending MUST be toggleable per assignment at creation/update time.
- **FR-093**: Reminder emails MUST be schedulable relative to each candidate's start time (defaults: 24 h and 1 h before) and skip completed/removed candidates.
- **FR-094**: Every email MUST record delivery status (queued, sent, delivered, bounced, failed) visible per candidate; failures are surfaced to admins.

### Non-Functional Requirements

- **NFR-001 (Performance)**: p95 API latency < 300 ms for exam-critical endpoints (answer save, navigation, timer sync) under 1,000 concurrent candidates.
- **NFR-002 (Autosave durability)**: no more than 3 s of answer input may be lost on crash/disconnect.
- **NFR-003 (Availability)**: exam-taking path targets 99.9% availability during scheduled windows.
- **NFR-004 (Scalability)**: code execution scales horizontally via worker pool; queue depth and wait time observable.
- **NFR-005 (Security)**: OWASP ASVS L2; rate limiting on auth endpoints; all candidate uploads virus-size-type validated; signed URLs expire ≤ 15 min.
- **NFR-006 (Privacy/retention)**: proctoring evidence retention is configurable per organization (default 90 days), after which evidence is purged; audit logs are retained indefinitely.
- **NFR-007 (Observability)**: structured logs with request ids, metrics for queue depth, execution latency, WebSocket connections, email failures; alerting on runner and email outages.
- **NFR-008 (Accessibility)**: admin panel and candidate UI meet WCAG 2.1 AA where compatible with proctoring constraints.

### Key Entities *(data involved — details in data-model.md)*

- **Organization** — tenant boundary; owns users, assessments, questions.
- **User** — admin-side account; has roles (`hr_admin`, `test_creator`, `evaluator`).
- **AuditLog** — append-only record of sensitive actions.
- **Assessment** — the test container; has versions.
- **AssessmentVersion** — frozen snapshot of sections/questions/rules once any candidate starts.
- **Section** — ordered part of an assessment version with duration, weightage, types, count, pool rules.
- **Question / QuestionVersion** — bank item with type, category, difficulty, metadata; versioned on edit.
- **QuestionPoolRule** — "select N of M" configuration per section.
- **Candidate** — person identity (name, email, phone) — exists only via assignments.
- **TestAssignment** — links candidate ↔ assessment with window, credentials, email toggle, status.
- **ExamSession** — a candidate's active attempt: state machine, section progress, resume data.
- **Answer** — per-question latest checkpointed response with history of checkpoints.
- **CodeSubmission** — every run/submit: code, language, per-case results, time, memory, score.
- **ProctoringEvent / Evidence** — events and screenshot/audio evidence with storage refs.
- **Evaluation** — per-answer scoring record (auto/AI-suggested/human-final) with override trail.
- **Report** — compiled candidate result + AI observations; export artifacts.
- **EmailMessage** — every outbound email with type, payload ref, delivery status.

---

## Review & Acceptance Checklist

### Content Quality
- [x] No implementation details leak into FRs (stack lives in plan.md; FRs name capabilities)
- [x] Focused on user value and business needs
- [x] All mandatory sections completed

### Requirement Completeness
- [x] Requirements are testable and unambiguous
- [x] Success criteria measurable (NFRs quantified)
- [x] Scope bounded: no global student module, no candidate self-registration, no payment/billing, no multi-language UI (English only) in v1
- [x] Dependencies identified: Judge0/runner, Resend, object storage, AI provider

### Open Items (resolved defaults — flag if product disagrees)
- [ ] Concurrent-login policy: reject new login (default) vs. terminate old session — configurable, default = reject new.
- [ ] Section timing pause on runner outage: not paused by default; admin remedy = new session.
- [ ] Percentile threshold default = 20; negative marking default = off.
- [ ] Screenshot cadence default = 5 s; retention default = 90 days.

---

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked (Open Items with proposed defaults)
- [x] User scenarios defined
- [x] Requirements generated (FR-001 … FR-094, NFR-001 … NFR-008)
- [x] Entities identified
- [x] Review checklist passed
