"""SQLite persistence layer (engine, session, and repository helpers).

Routes run in FastAPI's threadpool (sync `def`) and the RabbitMQ consumer runs
on the event loop, so SQLite is opened with ``check_same_thread=False`` and put
into WAL mode for better read/write concurrency. Repository helpers return
plain dicts (never live ORM objects) so callers don't trip over detached
instances after the session closes.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from .config import get_settings
from .models import Deployment, utcnow

settings = get_settings()

_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
    """Enable WAL + a busy timeout to reduce 'database is locked' errors."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
    except Exception:
        # Non-SQLite backends raise here; safe to ignore.
        pass


def init_db() -> None:
    """Create the data directory (for file-based SQLite) and all tables."""
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.replace("sqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


# --------------------------------------------------------------------------- #
# Repository helpers
# --------------------------------------------------------------------------- #
def upsert_deployment(
    *, id: str, name: str, image: str, status: str, source: str = "api"
) -> dict:
    with get_session() as session:
        record = session.get(Deployment, id)
        if record is None:
            record = Deployment(
                id=id, name=name, image=image, status=status, source=source
            )
        else:
            record.name = name
            record.image = image
            record.status = status
            record.source = source
            record.updated_at = utcnow()
        session.add(record)
        session.commit()
        session.refresh(record)
        return record.model_dump()


def update_status(container_id: str, status: str) -> None:
    with get_session() as session:
        record = session.get(Deployment, container_id)
        if record is not None:
            record.status = status
            record.updated_at = utcnow()
            session.add(record)
            session.commit()


def mark_deleted(container_id: str) -> None:
    update_status(container_id, "deleted")


def get_deployment(container_id: str) -> dict | None:
    with get_session() as session:
        record = session.get(Deployment, container_id)
        return record.model_dump() if record is not None else None


def list_deployments() -> list[dict]:
    with get_session() as session:
        rows = session.exec(
            select(Deployment).order_by(Deployment.updated_at.desc())
        ).all()
        return [row.model_dump() for row in rows]
