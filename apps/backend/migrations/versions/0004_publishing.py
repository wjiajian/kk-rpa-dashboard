"""Git sources, immutable releases and robot installation jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"


def upgrade():
    op.add_column("robots", sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("robots", sa.Column("deployment_job", sa.String(), nullable=True))
    op.create_table("application_sources", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False), sa.Column("url", sa.String(), nullable=False),
        sa.Column("encrypted_credentials", sa.String(), nullable=True))
    op.create_table("import_jobs", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("application_sources.id"), nullable=False),
        sa.Column("created", sa.Float(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False))
    op.create_table("applications", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("application_sources.id"), nullable=False),
        sa.Column("app_id", sa.String(), nullable=False), sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("source_id", "app_id", name="uq_source_app"))
    op.create_table("application_releases", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("application_id", sa.String(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("commit", sa.String(), nullable=False), sa.Column("version", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False), sa.UniqueConstraint("application_id", "commit", name="uq_app_commit"))
    op.create_table("robot_deployments",
        sa.Column("robot_id", sa.String(), sa.ForeignKey("robots.id"), primary_key=True),
        sa.Column("release_id", sa.String(), sa.ForeignKey("application_releases.id"), primary_key=True),
        sa.Column("status", sa.String(), nullable=False), sa.Column("data", sa.JSON(), nullable=False))
    op.create_table("deployment_jobs", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("robot_id", sa.String(), sa.ForeignKey("robots.id"), nullable=False),
        sa.Column("release_id", sa.String(), sa.ForeignKey("application_releases.id"), nullable=False),
        sa.Column("created", sa.Float(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False))
    op.create_index("ix_deployment_jobs_robot_id", "deployment_jobs", ["robot_id"])


def downgrade():
    op.drop_index("ix_deployment_jobs_robot_id", table_name="deployment_jobs")
    for table in ("deployment_jobs", "robot_deployments", "application_releases", "applications", "import_jobs", "application_sources"):
        op.drop_table(table)
    op.drop_column("robots", "deployment_job")
    op.drop_column("robots", "capabilities")
