from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Question, QuestionVersion

DUPLICATE_THRESHOLD = 0.85


def structural_errors(qtype: str, config: dict) -> list[str]:
    """Hard validation per question type (FR-047). Returns error strings."""
    errors: list[str] = []
    if qtype == "mcq":
        options = config.get("options") or []
        correct = config.get("correct_option_ids") or []
        option_ids = {o.get("id") for o in options if isinstance(o, dict)}
        if len(options) < 2:
            errors.append("mcq requires at least 2 options")
        if not correct:
            errors.append("mcq requires at least 1 correct option")
        if set(correct) - option_ids:
            errors.append("correct_option_ids must reference existing options")
    elif qtype == "coding":
        cases = config.get("test_cases") or []
        if not cases:
            errors.append("coding question requires test cases")
        for case in cases:
            if "input" not in case or "expected_output" not in case:
                errors.append("each test case needs input and expected_output")
                break
        langs = config.get("allowed_languages") or []
        if not langs:
            errors.append("coding question requires allowed_languages")
    elif qtype == "text":
        if not (config.get("rubric") or config.get("expected_answer")):
            errors.append("text question requires a rubric or expected answer")
    else:
        errors.append(f"unknown question type: {qtype}")
    return errors


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def find_duplicates(
    db: AsyncSession,
    org_id: str,
    title: str,
    body: str,
    exclude_question_id: str | None = None,
    statuses: tuple[str, ...] = ("active",),
) -> list[dict]:
    """Near-duplicate detection against the bank. Uses difflib similarity,
    which is portable; Postgres deployments may switch to pg_trgm (research R15)."""
    q = (
        select(QuestionVersion, Question)
        .join(Question, Question.current_version_id == QuestionVersion.id)
        .where(Question.org_id == org_id, Question.status.in_(statuses))
    )
    if exclude_question_id:
        q = q.where(Question.id != exclude_question_id)
    rows = (await db.execute(q)).all()
    text = f"{title}\n{body}"
    hits = []
    for version, question in rows:
        score = similarity(text, f"{version.title}\n{version.body}")
        if score >= DUPLICATE_THRESHOLD:
            hits.append({"question_id": question.id, "similarity": round(score, 3)})
    return hits
