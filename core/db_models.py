from sqlmodel import SQLModel, Field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Subdomain(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    target: str = Field(index=True)
    subdomain: str = Field(index=True)
    source_plugin: str
    first_seen: datetime = Field(default_factory=_utc_now)
    last_seen: datetime = Field(default_factory=_utc_now)