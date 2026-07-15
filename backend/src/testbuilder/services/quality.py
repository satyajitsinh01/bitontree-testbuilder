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
        errors.extend(_coding_errors(config))
    elif qtype == "text":
        if not (config.get("rubric") or config.get("expected_answer")):
            errors.append("text question requires a rubric or expected answer")
    else:
        errors.append(f"unknown question type: {qtype}")
    return errors


def _coding_errors(config: dict) -> list[str]:
    """Coding questions come in two shapes: LeetCode-style (a typed `signature`
    with `args`/`expected` cases) or legacy stdin/stdout (`input`/`expected_output`)."""
    from . import harness

    errors: list[str] = []
    langs = config.get("allowed_languages") or []
    if not langs:
        errors.append("coding question requires allowed_languages")
    cases = config.get("test_cases") or []
    if not cases:
        errors.append("coding question requires test cases")

    signature = config.get("signature")
    if signature is not None:
        sig_errors = harness.validate_signature(signature)
        errors.extend(sig_errors)
        if not sig_errors:
            n_params = len(signature["params"])
            starter = config.get("starter_code") or {}
            for lang in langs:
                if lang not in harness.languages_supporting(signature):
                    errors.append(
                        f"language '{lang}' cannot execute this signature's types"
                    )
                elif not starter.get(lang):
                    errors.append(f"starter_code missing for language '{lang}'")
            for case in cases:
                if not isinstance(case.get("args"), list) or "expected" not in case:
                    errors.append("each test case needs 'args' (list) and 'expected'")
                    break
                if len(case["args"]) != n_params:
                    errors.append(
                        f"test case '{case.get('id')}' has {len(case['args'])} args, "
                        f"signature expects {n_params}"
                    )
                    break
            if not any(c.get("is_hidden") for c in cases):
                errors.append("coding question should include at least one hidden test case")
    else:
        # legacy stdin/stdout questions
        for case in cases:
            if "input" not in case or "expected_output" not in case:
                errors.append("each test case needs input and expected_output")
                break
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
