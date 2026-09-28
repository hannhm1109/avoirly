"""Operator-only, non-content metrics and conservative reported-usage estimates."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

from .db.models import DeletionTask, Job, ModelUsage, WorkerHeartbeat


def usage_record(settings, model, metadata):
    usage = metadata.get("token_usage") or {}
    incoming, outgoing = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if (
        not isinstance(incoming, int)
        or not isinstance(outgoing, int)
        or min(incoming, outgoing) < 0
    ):
        return None
    estimate = None
    try:
        a, b = Decimal(settings.input_usd_per_million), Decimal(settings.output_usd_per_million)
        if model == settings.model and a.is_finite() and b.is_finite() and min(a, b) >= 0:
            estimate = (incoming * a + outgoing * b) / Decimal(1_000_000)
    except InvalidOperation:
        pass
    return ModelUsage(
        model=model, input_tokens=incoming, output_tokens=outgoing, estimated_usd=estimate
    )


def metrics(sessions):
    with sessions() as session:
        now = session.scalar(select(func.clock_timestamp()))
        counts = dict(session.execute(select(Job.status, func.count()).group_by(Job.status)).all())
        seen = session.scalar(select(func.max(WorkerHeartbeat.last_seen)))
        stale = session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == "RUNNING", Job.leased_until < now)
        )
        failures = session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == "FAILED", Job.created_at >= now - timedelta(hours=24))
        )
        cleanup = session.scalar(select(func.count()).select_from(DeletionTask))
        usage = session.execute(
            select(
                ModelUsage.model,
                func.sum(ModelUsage.input_tokens),
                func.sum(ModelUsage.output_tokens),
                func.sum(ModelUsage.estimated_usd),
                func.count().filter(ModelUsage.estimated_usd.is_(None)),
            )
            .where(ModelUsage.created_at >= now - timedelta(hours=24))
            .group_by(ModelUsage.model)
        ).all()
        return {
            "checked_at": now.isoformat(),
            "jobs": counts,
            "expired_leases": stale,
            "failures_24h": failures,
            "pending_file_deletions": cleanup,
            "worker_healthy": bool(seen and seen >= now - timedelta(minutes=3)),
            "worker_last_seen": seen.isoformat() if seen else None,
            "reported_usage_24h": [
                {
                    "model": m,
                    "input_tokens": i,
                    "output_tokens": o,
                    "estimated_usd": str(cost) if cost is not None else None,
                    "unpriced_records": unknown,
                }
                for m, i, o, cost, unknown in usage
            ],
        }
