"""Reusable plans, encrypted plan credentials and persistent trigger deduplication."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table("tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("robot_id", sa.String(), sa.ForeignKey("robots.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.Float(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False))
    op.create_index("ix_tasks_robot_id", "tasks", ["robot_id"])
    op.create_index("ix_tasks_next_run_at", "tasks", ["next_run_at"])
    op.create_table("task_credentials",
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("encrypted", sa.String(), nullable=False))
    op.create_table("run_triggers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False, unique=True),
        sa.Column("intent", sa.JSON(), nullable=False))


def downgrade():
    op.drop_table("run_triggers")
    op.drop_table("task_credentials")
    op.drop_index("ix_tasks_next_run_at", table_name="tasks")
    op.drop_index("ix_tasks_robot_id", table_name="tasks")
    op.drop_table("tasks")
