from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Subdomain(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    target: str = Field(index=True)
    subdomain: str = Field(index=True)
    source_plugin: str
    alive: bool | None = Field(default=None)
    status_code: int | None = Field(default=None)
    title: str | None = Field(default=None)
    first_seen: datetime = Field(default_factory=_utc_now)
    last_seen: datetime = Field(default_factory=_utc_now)

#class Webservers(SQLModel, table=True):
#    id: int = Field(default=None, primary_key=True)
#    subdomain: str = ForeignKey('Subdomain', table=False)
#    status_code: int = Field(default=None)
#    title : str = Field(default=None)
#    tech : list[str] = Field(default=None)
#    a_record : list[str] = Field(default=None)

