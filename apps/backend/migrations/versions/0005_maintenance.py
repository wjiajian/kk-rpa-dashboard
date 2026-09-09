"""Persistent maintenance gate for triggers and dispatch."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"


def upgrade():
    table = op.create_table("service_state", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("maintenance", sa.Boolean(), nullable=False))
    op.bulk_insert(table, [{"id": 1, "maintenance": False}])


def downgrade():
    op.drop_table("service_state")
