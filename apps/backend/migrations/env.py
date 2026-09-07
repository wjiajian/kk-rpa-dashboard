import os
from alembic import context
from sqlalchemy import create_engine
from rpa_console.storage import Base

engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
