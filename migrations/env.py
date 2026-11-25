"""Alembic environment for the RHEA canonical store."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from rhea.core.config import get_settings
from rhea.stores.relational import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

dsn = get_settings().postgres_dsn
if not dsn:
    raise RuntimeError(
        "RHEA_POSTGRES_DSN is not configured. Set it before running migrations."
    )


def run_migrations_offline() -> None:
    context.configure(url=dsn, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(dsn, poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
