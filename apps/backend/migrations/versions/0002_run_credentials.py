"""Encrypted credentials submitted with each console run."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table("run_credentials",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), primary_key=True),
        sa.Column("encrypted", sa.String(), nullable=False))


def downgrade():
    op.drop_table("run_credentials")
