"""AI capability boundary (research R9). All features run against Google Gemini via
the google-genai SDK when TB_GEMINI_API_KEY is set; otherwise a deterministic local
stub keeps development and tests working offline. Every caller stores prompt/model
metadata alongside the output (Constitution V)."""

import json

import structlog

from ..config import get_settings

log = structlog.get_logger()

GENERATION_SCHEMA_HINT = (
    "Return strict JSON: {\"questions\": [{\"title\": str, \"body\": str, "
    "\"qtype\": \"mcq\"|\"text\"|\"coding\", \"difficulty\": \"easy\"|\"medium\"|\"hard\", "
    "\"config\": object, \"topic\": str, \"skills\": [str]}]}. "
    "For mcq config: {options: [{id, text}], correct_option_ids: [id]}. "
    "For text config: {rubric, expected_answer}. "
    "For coding config: {allowed_languages, starter_code, test_cases: "
    "[{id, input, expected_output, is_hidden, weight}]}."
)


def _client():
    from google import genai  # imported lazily; optional dependency

    return genai.Client(api_key=get_settings().gemini_api_key)


def _gemini_json(prompt: str) -> dict:
    settings = get_settings()
    client = _client()
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return json.loads(response.text)


def _stub_questions(qtype: str, count: int, difficulty: str, topic: str) -> list[dict]:
    import uuid

    questions = []
    for i in range(count):
        # unique marker per question so stub output survives similarity dedupe,
        # like genuinely distinct model output would
        marker = uuid.uuid4().hex[:10]
        if qtype == "mcq":
            config = {
                "options": [{"id": f"o{j}", "text": f"Option {j + 1}"} for j in range(4)],
                "correct_option_ids": ["o0"],
            }
            answer_type = "single_choice"
        elif qtype == "coding":
            config = {
                "allowed_languages": ["python", "javascript"],
                "starter_code": {"python": "def solve():\n    pass\n"},
                "test_cases": [
                    {"id": "t1", "input": "1", "expected_output": "1", "is_hidden": False,
                     "weight": 1},
                    {"id": "t2", "input": "2", "expected_output": "2", "is_hidden": True,
                     "weight": 2},
                ],
            }
            answer_type = "code"
        else:
            config = {"rubric": f"Assess understanding of {topic}", "expected_answer": ""}
            answer_type = "long_text"
        questions.append(
            {
                "title": f"[draft {marker}] {topic} {difficulty} question {i + 1}",
                "body": f"Stub {qtype} about {topic}, variant {marker} "
                "(set TB_GEMINI_API_KEY for real generation).",
                "qtype": qtype,
                "answer_type": answer_type,
                "difficulty": difficulty,
                "config": config,
                "topic": topic,
                "skills": [topic],
            }
        )
    return questions


def generate_questions(
    prompt: str,
    qtype: str,
    count: int,
    difficulty: str,
    topic: str,
    skills: list[str],
    avoid_titles: list[str] | None = None,
) -> tuple[list[dict], str]:
    """Returns (questions, model_used). Raises ValueError on unusable AI output.
    avoid_titles feeds existing bank questions into the prompt so the model does
    not regenerate them; the caller additionally dedupes by similarity."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return _stub_questions(qtype, count, difficulty, topic), "stub"
    avoid_clause = ""
    if avoid_titles:
        joined = "; ".join(avoid_titles[:40])
        avoid_clause = (
            f"\nIMPORTANT: do NOT repeat or rephrase these existing questions: {joined}"
        )
    full_prompt = (
        f"Generate {count} {difficulty}-difficulty {qtype} assessment questions on "
        f"'{topic}' (skills: {', '.join(skills) or topic}). Admin instructions: {prompt}"
        f"{avoid_clause}\n" + GENERATION_SCHEMA_HINT
    )
    data = _gemini_json(full_prompt)
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("AI returned no questions")
    for q in questions:
        q.setdefault("answer_type", {
            "mcq": "single_choice", "coding": "code", "text": "long_text"
        }.get(q.get("qtype", qtype), "long_text"))
    return questions, settings.gemini_model


def evaluate_written(rubric: str, expected: str, answer: str, max_score: float) -> dict:
    """Returns {score, rationale, confidence}."""
    settings = get_settings()
    if not answer.strip():
        return {"score": 0.0, "rationale": "No answer provided.", "confidence": 1.0}
    if not settings.gemini_api_key:
        # deterministic stub: keyword overlap against rubric/expected answer
        reference = f"{rubric} {expected}".lower().split()
        hits = sum(1 for w in set(answer.lower().split()) if w in reference)
        ratio = min(1.0, hits / max(len(set(reference)), 1) * 3)
        return {
            "score": round(max_score * ratio, 2),
            "rationale": "Stub keyword-overlap evaluation (set TB_GEMINI_API_KEY).",
            "confidence": 0.3,
        }
    data = _gemini_json(
        f"Score this answer against the rubric. Rubric: {rubric}\nExpected: {expected}\n"
        f"Answer: {answer}\nMax score: {max_score}. "
        'Return strict JSON {"score": number, "rationale": str, "confidence": 0..1}.'
    )
    return {
        "score": max(0.0, min(float(data.get("score", 0)), max_score)),
        "rationale": str(data.get("rationale", "")),
        "confidence": max(0.0, min(float(data.get("confidence", 0.5)), 1.0)),
    }


def summarize_performance(report_payload: dict) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        pct = 0.0
        if report_payload.get("overall_max"):
            pct = report_payload["overall_score"] / report_payload["overall_max"] * 100
        return (
            f"[AI-generated] Candidate scored {report_payload.get('overall_score', 0):.1f}/"
            f"{report_payload.get('overall_max', 0):.1f} ({pct:.0f}%). "
            "Enable Gemini for a detailed narrative."
        )
    data = _gemini_json(
        "Summarize this assessment result for a recruiter in <=120 words. Mention strengths "
        "and weaknesses per section. Return strict JSON {\"summary\": str}. Data: "
        + json.dumps(report_payload)
    )
    return "[AI-generated] " + str(data.get("summary", ""))


def analyze_frame_stub(object_key: str) -> dict:
    """Screenshot analysis placeholder used when Gemini is unavailable."""
    return {"flags": [], "confidence": 0.0, "note": "analysis skipped (no API key)"}
