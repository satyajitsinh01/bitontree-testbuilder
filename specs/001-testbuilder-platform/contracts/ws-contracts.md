# WebSocket Contracts: TestBuilder Platform

Endpoint: `wss://<host>/ws`. Auth via `?token=<access_jwt>` on connect (validated before upgrade). Messages are JSON: `{ "type": string, "ts": iso8601, "payload": object }`. Heartbeat: client sends `ping` every 15 s; server replies `pong` with `server_now` (drift sync + Redis session-lock refresh, R2/R3).

---

## Channel 1: Candidate exam session  `/ws/exam`

Scope: one connection per active exam session. A second connection with the same session token closes the first with code `4001 superseded`; a connection for an assignment whose session is owned elsewhere is refused `4002 session_active_elsewhere`.

### Server → Client

| type | payload | purpose |
| --- | --- | --- |
| `session.state` | `{server_now, session_status, current_section_id, section_deadline_at, exam_ends_at}` | On connect/reconnect and every 30 s (authoritative timer, R3) |
| `section.expired` | `{section_id, next_section_id \| null, auto_submitted: true}` | Server auto-submitted the section (FR-036) |
| `exam.auto_submitted` | `{reason: "time_up" \| "window_end"}` | Whole exam force-submitted (FR-037) |
| `session.terminated` | `{reason: "admin_reset" \| "superseded"}` | Admin created a new session or duplicate login policy fired |
| `code.result` | `{submission_id, status, results[], exec_time_ms, memory_kb, score?}` | Push Judge0 outcome (visible-case filtered per question config) |
| `proctor.warning` | `{kind, severity, message}` | On-screen warning echo (e.g., fullscreen_exit) |
| `answer.ack` | `{sqid, saved_at}` | Ack for WS-path autosaves |

### Client → Server

| type | payload | purpose |
| --- | --- | --- |
| `ping` | `{}` | Heartbeat / lock refresh |
| `answer.save` | `{sqid, payload, idempotency_key}` | Autosave fast path (REST fallback exists) |
| `proctor.event` | `{kind, occurred_at, detail}` | tab_switch, window_blur, fullscreen_exit, copy_attempt, paste_attempt, camera_lost, mic_lost (FR-071) |
| `question.state` | `{sqid, state: seen \| marked_review}` | Progress palette sync (FR-054) |

Reconnect contract: client reconnects with same token → server replays `session.state`; answers never depend on WS delivery (REST autosave is the durability path).

## Channel 2: Admin live monitor  `/ws/admin/assessments/{id}`

Role: hr_admin or evaluator. Read-only fan-out.

| type (S→C) | payload | purpose |
| --- | --- | --- |
| `candidate.status` | `{assignment_id, status, section_id, progress: {attempted, unattempted, marked}}` | Live grid of in-progress candidates |
| `proctor.flag` | `{assignment_id, session_id, kind, severity, evidence_thumb_url?}` | Real-time red flags/warnings (FR-075) |
| `session.event` | `{assignment_id, event: started \| section_submitted \| completed \| terminated}` | Timeline feed |

## Close codes

| code | meaning |
| --- | --- |
| 4000 | invalid/expired token |
| 4001 | superseded by newer connection (same session) |
| 4002 | active session exists elsewhere |
| 4003 | session ended (submitted/terminated) |
