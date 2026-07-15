"""
backend/core/database.py
────────────────────────
SQLAlchemy 2.0 database layer — engine, session factory, and declarative base.

Components created here:
  - engine        : The connection pool to PostgreSQL. Created once at startup.
  - SessionLocal  : A factory that produces new DB sessions on demand.
  - Base          : The declarative base class. All ORM models inherit from this.
  - get_db()      : FastAPI dependency that yields a scoped session per request
                    and guarantees cleanup via try/finally.

Why pool_pre_ping=True?
  PostgreSQL drops idle connections after a timeout. pool_pre_ping sends a
  lightweight SELECT 1 before reusing a stale connection, preventing errors.

Why pool_size / max_overflow?
  - pool_size     : Persistent connections kept alive between requests.
  - max_overflow  : Extra connections allowed during traffic spikes.
  Total maximum connections = pool_size + max_overflow (default: 30).

SQLAlchemy 2.0 notes:
  - DeclarativeBase is the new-style base (replaces declarative_base()).
  - Sessions use autocommit=False — you must call db.commit() explicitly.

Usage:
    from backend.core.database import get_db, Base

    # In a FastAPI route:
    def my_route(db: Session = Depends(get_db)):
        ...

    # In an ORM model:
    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings


# ── Engine ────────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # Validate connections before reuse
    pool_size=10,             # Persistent connection pool size
    max_overflow=20,          # Burst connections beyond pool_size
    echo=settings.DEBUG,      # Log all SQL statements when DEBUG=True
)

# ── Session Factory ──────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,   # Explicit commits required
    autoflush=False,    # Don't auto-flush before queries — we control this
    class_=Session,
)


# ── Declarative Base ─────────────────────────────────────────
class Base(DeclarativeBase):
    """
    SQLAlchemy 2.0 declarative base.

    All ORM model classes must inherit from this Base.
    Base.metadata holds the registry of all tables, which Alembic
    reads to generate migrations automatically.

    Example:
        class User(Base):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)
    """
    pass


# ── FastAPI Dependency ────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    Yields a database session scoped to a single HTTP request.

    The session is automatically closed when the request ends,
    even if an exception is raised. This prevents connection leaks.

    Inject with:
        def my_route(db: Session = Depends(get_db)):
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Database Health Check ─────────────────────────────────────
def check_database_connection() -> bool:
    """
    Verifies that the database is reachable.

    Returns True if the connection succeeds, False otherwise.
    Called during application startup to fail fast on misconfiguration.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
