"""Initial recovery control storage."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None

def upgrade():
    op.create_table("robots", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(), nullable=False),
        sa.Column("credential_hash", sa.String()), sa.Column("active_run", sa.String()), sa.Column("deployments", sa.JSON(), nullable=False))
    op.create_table("runs", sa.Column("id", sa.String(), primary_key=True), sa.Column("robot_id", sa.String(), sa.ForeignKey("robots.id"), nullable=False),
        sa.Column("created", sa.Float(), nullable=False), sa.Column("data", sa.JSON(), nullable=False))
    op.create_index("ix_runs_robot_id", "runs", ["robot_id"])
    op.create_table("operations", sa.Column("id", sa.String(), primary_key=True), sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False), sa.Column("data", sa.JSON(), nullable=False))
    op.create_index("ix_operations_run_id", "operations", ["run_id"])
    op.create_table("events", sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), primary_key=True), sa.Column("seq", sa.Integer(), primary_key=True), sa.Column("data", sa.JSON(), nullable=False))
    op.create_table("login_sessions", sa.Column("id", sa.String(), primary_key=True), sa.Column("expires", sa.Float(), nullable=False), sa.Column("data", sa.JSON(), nullable=False))
    op.create_table("evidence", sa.Column("id", sa.String(), primary_key=True), sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False), sa.Column("mime", sa.String(), nullable=False))
    op.create_index("ix_evidence_run_id", "evidence", ["run_id"])

def downgrade():
    for table in ("evidence", "events", "operations", "runs", "robots", "login_sessions"):
        op.drop_table(table)
