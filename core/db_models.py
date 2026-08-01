"""SQLModel database models for subdomain enumeration storage and sources tracking."""
from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Subdomain(SQLModel, table=True):
    """Database model mapping discovered subdomains to target domains and web status."""

    __table_args__ = (
        UniqueConstraint("target", "subdomain", name="uq_target_subdomain"),
    )

    id: int | None = Field(default=None, primary_key=True)
    target: str = Field(index=True)
    subdomain: str = Field(index=True)
    source_plugin: str
    alive: bool | None = Field(default=None)
    status_code: int | None = Field(default=None)
    title: str | None = Field(default=None)
    tech: str | None = Field(default=None)  # JSON list, e.g. '["Nginx","jQuery"]'
    first_seen: datetime = Field(default_factory=_utc_now)
    last_seen: datetime = Field(default_factory=_utc_now)

    # Relationships
    sources: list["SubdomainSource"] = Relationship(
        back_populates="subdomain",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SubdomainSource(SQLModel, table=True):
    """Join database model mapping subdomains to discovery plugin sources."""

    __tablename__ = "subdomain_sources"
    __table_args__ = (
        UniqueConstraint(
            "subdomain_id", "source_plugin", name="uq_subdomain_id_source_plugin"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    subdomain_id: int = Field(foreign_key="subdomain.id", index=True)
    source_plugin: str

    subdomain: Subdomain = Relationship(back_populates="sources")
