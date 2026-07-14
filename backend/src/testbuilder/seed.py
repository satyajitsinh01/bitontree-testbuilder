"""Seed a demo org, admin, question bank and a published assessment.

Run: uv run python -m testbuilder.seed
"""

import asyncio

from sqlalchemy import select

from .db import create_all, session_factory
from .models import Organization, Question, QuestionVersion, User, UserRole
from .security import hash_password

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin!Passw0rd"

SEED_MCQS = [
    ("Which HTTP method is idempotent by definition?",
     [("a", "PUT"), ("b", "POST"), ("c", "PATCH"), ("d", "CONNECT")], ["a"]),
    ("What does ACID stand for in databases?",
     [("a", "Atomicity Consistency Isolation Durability"),
      ("b", "Access Control Identity Data"),
      ("c", "Async Cache Index Disk"),
      ("d", "Apply Commit Insert Delete")], ["a"]),
    ("Which data structure gives O(1) average lookup?",
     [("a", "Hash table"), ("b", "Linked list"), ("c", "Binary tree"), ("d", "Stack")],
     ["a"]),
]


async def seed() -> None:
    await create_all()
    async with session_factory()() as db:
        existing = (
            await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"Seed already applied. Admin: {ADMIN_EMAIL}")
            return
        org = Organization(name="Demo Org", slug="demo")
        db.add(org)
        await db.flush()
        admin = User(
            org_id=org.id,
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            full_name="Demo Admin",
        )
        db.add(admin)
        await db.flush()
        for role in ("hr_admin", "test_creator", "evaluator"):
            db.add(UserRole(user_id=admin.id, role=role))
        for title, options, correct in SEED_MCQS:
            question = Question(
                org_id=org.id, status="active", source="manual", created_by=admin.id
            )
            db.add(question)
            await db.flush()
            version = QuestionVersion(
                question_id=question.id,
                version=1,
                qtype="mcq",
                answer_type="single_choice",
                title=title,
                body=title,
                config={
                    "options": [{"id": oid, "text": text} for oid, text in options],
                    "correct_option_ids": correct,
                },
                topic="fundamentals",
                skills=["backend"],
            )
            db.add(version)
            await db.flush()
            question.current_version_id = version.id
        await db.commit()
        print(f"Seeded. Admin login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
