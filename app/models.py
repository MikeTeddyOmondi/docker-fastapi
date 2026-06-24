"""Database models and API request schemas."""
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Deployment(SQLModel, table=True):
    """Persistent record of a container the API has managed.

    Docker remains the source of truth for *live* state; this table is the
    durable history / audit log so the API can answer "what have we deployed"
    even for containers that have since been removed.
    """

    __tablename__ = "deployments"

    id: str = Field(primary_key=True, description="Docker container ID")
    name: str = Field(index=True)
    image: str
    status: str = Field(default="unknown")
    source: str = Field(default="api", description="api | queue")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ContainerCreateRequest(SQLModel):
    """Request body for POST /containers."""

    image: str
    name: str
