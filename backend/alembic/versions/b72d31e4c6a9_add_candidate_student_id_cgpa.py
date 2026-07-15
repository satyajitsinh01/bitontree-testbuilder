"""add candidate student id and cgpa

Revision ID: b72d31e4c6a9
Revises: 95902b6a277d
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b72d31e4c6a9"
down_revision: Union[str, None] = "95902b6a277d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("student_id", sa.String(length=100), nullable=True))
    op.add_column("candidates", sa.Column("cgpa", sa.Float(), nullable=True))
    op.create_index(op.f("ix_candidates_student_id"), "candidates", ["student_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_candidates_student_id"), table_name="candidates")
    op.drop_column("candidates", "cgpa")
    op.drop_column("candidates", "student_id")
