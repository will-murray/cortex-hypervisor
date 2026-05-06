"""
Alembic environment for the cortex-hypervisor Cloud SQL config store.

Online mode reuses the application engine from api.core.db (IAM auth via
google-cloud-sql-python-connector). Offline mode is unsupported for now —
all production DDL flows through online migrations against the live instance.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

# Ensure the hypervisor package root is on sys.path so `from api...` imports
# resolve the same way as in the running app.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alembic import context  # noqa: E402

from api.core.db import get_engine  # noqa: E402
from api.core.orm import Base  # noqa: E402


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    raise RuntimeError(
        "Offline migrations are unsupported. Run `alembic upgrade head` against "
        "the live Cloud SQL instance using IAM auth."
    )


def run_migrations_online() -> None:
    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
