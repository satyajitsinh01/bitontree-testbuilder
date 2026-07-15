"""add fixed assessment window

Revision ID: c84f19a27d10
Revises: b72d31e4c6a9
Create Date: 2026-07-15
"""

from datetime import UTC, datetime, timedelta
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c84f19a27d10"
down_revision: Union[str, None] = "b72d31e4c6a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("window_start_at", sa.DateTime(), nullable=True))
    op.add_column("assessments", sa.Column("window_end_at", sa.DateTime(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT a.id, COALESCE(SUM(s.duration_min), 60) AS duration_min "
            "FROM assessments a "
            "LEFT JOIN assessment_versions v ON v.id = a.current_version_id "
            "LEFT JOIN sections s ON s.assessment_version_id = v.id "
            "GROUP BY a.id"
        )
    ).mappings()
    start = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
    for row in rows:
        duration = max(1, int(row["duration_min"] or 60))
        bind.execute(
            sa.text(
                "UPDATE assessments SET window_start_at = :start, window_end_at = :end "
                "WHERE id = :assessment_id"
            ),
            {
                "start": start,
                "end": start + timedelta(minutes=duration),
                "assessment_id": row["id"],
            },
        )


def downgrade() -> None:
    op.drop_column("assessments", "window_end_at")
    op.drop_column("assessments", "window_start_at")
