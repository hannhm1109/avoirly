"""Call inside the same transaction and owner advisory lock as the mutation."""

from sqlalchemy import func, select

from .api.errors import DomainError
from .db.models import UsageCounter


def consume(session, owner, kind, limit):
    day = session.scalar(select(func.timezone("UTC", func.clock_timestamp()))).date()
    row = session.get(UsageCounter, (owner, day, kind))
    if row is None:
        row = UsageCounter(owner_id=owner, day=day, kind=kind, used=0)
        session.add(row)
    if row.used >= limit:
        raise DomainError(
            "DAILY_QUOTA",
            "Daily pilot allowance reached. Try after 00:00 UTC.",
            429,
            details={"kind": kind, "limit": limit},
        )
    row.used += 1
