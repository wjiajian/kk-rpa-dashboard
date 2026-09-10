"""Add persistent administrator audit logs."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"


def upgrade():
    op.create_index("ix_runs_created", "runs", ["created"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor_open_id", sa.String(), nullable=False),
        sa.Column("actor_name", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("created", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_logs_actor_open_id", "audit_logs", ["actor_open_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_target_id", "audit_logs", ["target_id"])
    op.create_index("ix_audit_logs_created", "audit_logs", ["created"])


def downgrade():
    op.drop_index("ix_audit_logs_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_target_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_open_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_runs_created", table_name="runs")
