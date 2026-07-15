"""
database/migrations/env.py
──────────────────────────
Alembic migration environment.

This file is executed by Alembic whenever you run any `alembic` command.
It connects the Alembic runner to:
  1. Our SQLAlchemy engine (via DATABASE_URL from Pydantic Settings).
  2. Our declarative Base.metadata (so Alembic knows all table definitions).

Two migration modes are supported:
  - Offline mode  : Generates SQL scripts without connecting to the DB.
                    Useful for DBA review or air-gapped environments.
  - Online mode   : Connects to the live DB and applies migrations directly.
                    This is the standard mode for development and CI/CD.

Adding models to autogenerate:
  Import your model modules BEFORE `target_metadata = Base.metadata` so
  SQLAlchemy registers their table definitions with Base.metadata.

  Example (Sprint 1+):
      from backend.models import user, bucket, file  # noqa: F401

  Without these imports, Alembic will not detect the tables and will
  generate empty (no-op) migrations.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Sys Path Setup ────────────────────────────────────────────
# Add the project root (CloudVault/) to sys.path so that
# `from backend.core.config import settings` resolves correctly
# when alembic is run from any working directory.
_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Project Imports ───────────────────────────────────────────
# These imports MUST come after the sys.path setup above.
from backend.core.config import settings          # noqa: E402
from backend.core.database import Base            # noqa: E402

# ── Model Imports for Autogenerate ───────────────────────────
# CRITICAL: Import ALL model modules here so SQLAlchemy registers
# their table definitions with Base.metadata before Alembic reads it.
# Without these imports, alembic revision --autogenerate produces empty migrations.
#
# Sprint 1:
from backend.models.user import User              # noqa: F401, E402
# Sprint 2:
from backend.models.aws_account import AWSAccount  # noqa: F401, E402
# Sprint 3:
from backend.models.bucket import Bucket            # noqa: F401, E402
# Sprint 4:
from backend.models.folder import Folder            # noqa: F401, E402
# Sprint 5:
from backend.models.file import File                # noqa: F401, E402
# Sprint 8:
from backend.models.shared_link import SharedLink    # noqa: F401, E402
# Sprint 10:
from backend.models.activity_log import ActivityLog  # noqa: F401, E402
from backend.models.notification import Notification  # noqa: F401, E402
#
# Sprint 11+: Add new model imports below as they are created:

# ── Alembic Config ────────────────────────────────────────────
config = context.config

# Inject the real DATABASE_URL from our Settings into alembic's config.
# This overrides the empty `sqlalchemy.url =` in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from alembic.ini's [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object Alembic uses to detect table changes.
# When autogenerating, Alembic compares this against the live DB schema.
target_metadata = Base.metadata


# ── Offline Migration ─────────────────────────────────────────
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL statements to stdout or a file without connecting
    to the database. Useful for reviewing migrations before applying.

    Run with:
        alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,        # Detect column type changes
        compare_server_default=True,  # Detect server-side default changes
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online Migration ──────────────────────────────────────────
def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Opens a real connection to the database and applies pending migrations.
    This is the standard mode for `alembic upgrade head`.

    NullPool is used so Alembic does not hold connections after the
    migration completes — important for short-lived CLI processes.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pooling for CLI migrations
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ── Entry Point ───────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
