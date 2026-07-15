# CloudVault — Database Migrations

This directory is managed by **Alembic**.

## Commands (run from `CloudVault/` project root)

| Command | Description |
|---|---|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade -1` | Revert the last migration |
| `alembic revision --autogenerate -m "add users table"` | Generate a new migration from model changes |
| `alembic history` | Show migration history |
| `alembic current` | Show current DB revision |

## Adding Models (Sprint 1+)

Before autogenerating, import your model modules in `env.py`:

```python
# database/migrations/env.py
from backend.models import user, bucket, file  # noqa: F401
```

Without these imports, Alembic cannot detect the tables.

## Directory Layout

```
database/migrations/
├── env.py              ← Alembic runtime configuration
├── script.py.mako      ← Template for new migration files
├── README.md           ← This file
└── versions/           ← Auto-generated migration files go here
```
