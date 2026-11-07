from alembic import context

from app import models  # noqa: F401
from app.config import get_settings
from app.db import Base, _make_engine

target_metadata = Base.metadata
url = get_settings().database_url


def run_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=url.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_online():
    eng = _make_engine(url)
    with eng.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=url.startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()


run_offline() if context.is_offline_mode() else run_online()
