"""Owner-checked manual recovery ledger. No network or automatic sending here."""

import hashlib
import json
import unicodedata
from datetime import UTC, timedelta
from decimal import Decimal, localcontext
from uuid import uuid4

from sqlalchemy import func, select

from .api.errors import DomainError
from .db.models import IdempotencyKey, RecoveryEntry, RecoveryEvidence
from .quotas import consume
from .service import case_summary, change, current_draft, owned_case, owner_lock

TRACKING_STATES = ("CLAIM_SENT", "AWAITING_RESPONSE", "CREDIT_PROMISED", "CREDIT_CONFIRMED")


def clean(value):
    if not value.strip():
        raise DomainError("INVALID_INPUT", "A nonempty reference or note is required.", 422)
    return value.strip()


def active_entries(session, case):
    return list(
        session.scalars(
            select(RecoveryEntry).where(
                RecoveryEntry.case_id == case.id,
                RecoveryEntry.revision == case.current_revision,
                RecoveryEntry.voided_at.is_(None),
            )
        )
    )


def summary(session, case):
    # Dashboard totals must not load private note bodies or sent-draft snapshots.
    entries = list(
        session.execute(
            select(
                RecoveryEntry.kind,
                RecoveryEntry.amount_net,
                RecoveryEntry.currency,
            ).where(
                RecoveryEntry.case_id == case.id,
                RecoveryEntry.revision == case.current_revision,
                RecoveryEntry.voided_at.is_(None),
            )
        )
    )
    sent = next((e for e in entries if e.kind == "SENT"), None)
    with localcontext() as context:
        context.prec = 48
        promised = sum((e.amount_net for e in entries if e.kind == "PROMISE"), Decimal("0.00"))
        confirmed = sum((e.amount_net for e in entries if e.kind == "CREDIT"), Decimal("0.00"))
        amount = sent.amount_net if sent else Decimal("0.00")
        return {
            "currency": sent.currency if sent else case.currency,
            "sent_net": str(amount),
            "promised_net": str(promised),
            "confirmed_net": str(confirmed),
            "remaining_claim_net": str(amount - confirmed),
            "has_sent_record": sent is not None,
            "fully_credited": bool(sent and confirmed == amount),
        }


def detail(session, case):
    data = summary(session, case)
    data["entries"] = [
        {
            "id": str(e.id),
            "kind": e.kind,
            "revision": e.revision,
            "occurred_on": e.occurred_on.isoformat(),
            "amount_net": str(e.amount_net) if e.amount_net is not None else None,
            "currency": e.currency,
            "reference": e.reference,
            "note": e.note,
            "due_on": e.due_on.isoformat() if e.due_on else None,
            "evidence_id": str(e.evidence_id) if e.evidence_id else None,
            "snapshot": e.snapshot_json,
            "actor_id": str(e.actor_id),
            "created_at": e.created_at.isoformat(),
            "voided_at": e.voided_at.isoformat() if e.voided_at else None,
            "void_reason": e.void_reason,
        }
        for e in session.scalars(
            select(RecoveryEntry)
            .where(RecoveryEntry.case_id == case.id)
            .order_by(RecoveryEntry.created_at, RecoveryEntry.id)
        )
    ]
    data["evidence"] = [
        {
            "id": str(e.id),
            "original_name": e.original_name,
            "mime_type": e.mime_type,
            "page_count": e.page_count,
            "sha256": e.sha256,
            "created_at": e.created_at.isoformat(),
        }
        for e in session.scalars(
            select(RecoveryEvidence)
            .where(RecoveryEvidence.case_id == case.id)
            .order_by(RecoveryEvidence.created_at, RecoveryEvidence.id)
        )
    ]
    return data


def run_action(session, owner, case_id, request, key, action, settings, entry_id=None):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, lock=True)
    route = f"/cases/{case_id}/tracking/{action}" + (f"/{entry_id}" if entry_id else "")
    # UUID path plus action fits the existing 128-character route column.
    digest = hashlib.sha256(
        json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    previous = session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.owner_id == owner,
            IdempotencyKey.route == route,
            IdempotencyKey.key == key,
        )
    )
    now = session.scalar(select(func.clock_timestamp()))
    if previous:
        if previous.request_hash != digest:
            raise DomainError("IDEMPOTENCY_CONFLICT", "This key was used with a different payload.")
        # Manual financial records remain idempotent for the lifetime of the case.
        return previous.response
    if case.version != request.expected_version:
        raise DomainError("VERSION_CONFLICT", "Case changed; reload before retrying.")
    if case.status == "CLOSED":
        raise DomainError("CASE_CLOSED", "Closed cases cannot be changed.")
    consume(session, owner, "tracking", settings.daily_tracking)
    if action == "void":
        void_entry(session, case, owner, entry_id, request, now)
    elif action == "await":
        change(session, case, "await_response", actor=owner, target="AWAITING_RESPONSE")
    else:
        add_entry(session, case, owner, request, action, now)
    session.flush()
    response = {**case_summary(case), "recovery": summary(session, case)}
    session.add(
        IdempotencyKey(
            owner_id=owner,
            case_id=case.id,
            route=route,
            key=key,
            request_hash=digest,
            response=response,
            expires_at=now + timedelta(days=36500),
        )
    )
    return response


def add_entry(session, case, owner, request, action, now):
    if (
        session.scalar(
            select(func.count()).select_from(RecoveryEntry).where(RecoveryEntry.case_id == case.id)
        )
        >= 1000
    ):
        raise DomainError("TRACKING_LIMIT", "Maximum tracking history reached.", 429)
    entries = active_entries(session, case)
    sent = next((e for e in entries if e.kind == "SENT"), None)
    if action != "sent" and (case.status not in TRACKING_STATES or sent is None):
        raise DomainError("CLAIM_NOT_SENT", "Record the sent claim before supplier follow-up.")
    if request.occurred_on > now.astimezone(UTC).date() or (
        sent and request.occurred_on < sent.occurred_on
    ):
        raise DomainError("INVALID_TRACKING_DATE", "Use a date from sending through today.", 422)
    amount = Decimal(request.amount_net) if hasattr(request, "amount_net") else None
    currency = request.currency if hasattr(request, "currency") else case.currency
    if currency != case.currency or (amount is not None and amount <= 0):
        raise DomainError(
            "INVALID_TRACKING_AMOUNT", "Use a positive net amount in the case currency.", 422
        )
    reference = clean(
        getattr(request, "reference", getattr(request, "recipient", "Réponse fournisseur"))
    )
    reference_key = unicodedata.normalize("NFKC", reference).casefold()
    note = (
        clean(request.note)
        if hasattr(request, "note")
        else "Envoi externe déclaré par le propriétaire."
    )
    entry = RecoveryEntry(
        id=uuid4(),
        case_id=case.id,
        actor_id=owner,
        revision=case.current_revision,
        kind={"sent": "SENT", "note": "NOTE", "promise": "PROMISE", "credit": "CREDIT"}[action],
        occurred_on=request.occurred_on,
        amount_net=amount,
        currency=currency,
        reference=reference,
        reference_key=reference_key,
        note=note,
        snapshot_json={},
    )
    target, event = None, "supplier_note_recorded"
    if action == "sent":
        draft = current_draft(session, case)
        if case.status != "CLAIM_DRAFTED" or sent or not draft or draft.id != request.draft_id:
            raise DomainError(
                "NO_CURRENT_DRAFT", "Review and save the current draft before recording sending."
            )
        if amount > case.potential_credit_net:
            raise DomainError(
                "INVALID_TRACKING_AMOUNT",
                "Sent amount exceeds the validated potential credit.",
                422,
            )
        entry.snapshot_json = {
            "draft_id": str(draft.id),
            "draft_version": draft.version,
            "comparison_id": str(draft.comparison_id),
            "subject": draft.subject,
            "body": draft.body,
            "sent_outside_app": True,
        }
        target, event = "CLAIM_SENT", "claim_recorded_sent"
    elif action in ("promise", "credit"):
        kind = "PROMISE" if action == "promise" else "CREDIT"
        with localcontext() as context:
            context.prec = 48
            total = sum((e.amount_net for e in entries if e.kind == kind), Decimal("0.00")) + amount
        if total > sent.amount_net:
            raise DomainError(
                "CREDIT_EXCEEDS_CLAIM", "Cumulative amount exceeds the sent claim.", 422
            )
        if action == "promise":
            if request.due_on and request.due_on < request.occurred_on:
                raise DomainError(
                    "INVALID_TRACKING_DATE", "Due date cannot precede the promise.", 422
                )
            entry.due_on = request.due_on
            event = "credit_promised"
            target = (
                None
                if case.status in ("CREDIT_CONFIRMED", "CREDIT_PROMISED")
                else "CREDIT_PROMISED"
            )
        else:
            evidence = session.scalar(
                select(RecoveryEvidence).where(
                    RecoveryEvidence.id == request.evidence_id,
                    RecoveryEvidence.case_id == case.id,
                    RecoveryEvidence.owner_id == owner,
                )
            )
            if not evidence:
                raise DomainError("NOT_FOUND", "Credit evidence not found.", 404)
            if any(
                e.kind == "CREDIT"
                and (e.reference_key == reference_key or e.evidence_id == evidence.id)
                for e in entries
            ):
                raise DomainError(
                    "DUPLICATE_CREDIT", "This credit reference or evidence is already counted."
                )
            entry.evidence_id = evidence.id
            entry.snapshot_json = {
                "received_and_verified": True,
                "evidence_sha256": evidence.sha256,
            }
            event = "credit_confirmed"
            target = None if case.status == "CREDIT_CONFIRMED" else "CREDIT_CONFIRMED"
    session.add(entry)
    change(session, case, event, actor=owner, target=target, metadata={"entry_id": str(entry.id)})


def void_entry(session, case, owner, entry_id, request, now):
    entry = session.scalar(
        select(RecoveryEntry).where(
            RecoveryEntry.id == entry_id,
            RecoveryEntry.case_id == case.id,
            RecoveryEntry.revision == case.current_revision,
        )
    )
    if not entry:
        raise DomainError("NOT_FOUND", "Tracking entry not found.", 404)
    if entry.voided_at:
        raise DomainError("ENTRY_VOIDED", "This entry is already voided.")
    others = [e for e in active_entries(session, case) if e.id != entry.id]
    target, event = None, "tracking_entry_voided"
    if entry.kind == "SENT":
        if any(e.kind in ("PROMISE", "CREDIT") for e in others):
            raise DomainError(
                "ACTIVE_CREDITS", "Void promises and confirmed credits before correcting sending."
            )
        target, event = "CLAIM_DRAFTED", "sent_record_voided"
    elif entry.kind in ("CREDIT", "PROMISE"):
        next_status = (
            "CREDIT_CONFIRMED"
            if any(e.kind == "CREDIT" for e in others)
            else ("CREDIT_PROMISED" if any(e.kind == "PROMISE" for e in others) else "CLAIM_SENT")
        )
        if next_status != case.status:
            target = next_status
            event = (
                "tracking_promised" if next_status == "CREDIT_PROMISED" else "tracking_corrected"
            )
    entry.voided_at, entry.voided_by, entry.void_reason = now, owner, clean(request.reason)
    change(
        session,
        case,
        event,
        actor=owner,
        target=target,
        metadata={"entry_id": str(entry.id), "reason": entry.void_reason},
    )


def attach_evidence(session, owner, case_id, expected, fields, settings):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, expected, lock=True)
    if case.status not in TRACKING_STATES:
        raise DomainError("CLAIM_NOT_SENT", "Evidence belongs to a recorded sent claim.")
    prior = session.scalar(
        select(RecoveryEvidence).where(
            RecoveryEvidence.owner_id == owner,
            RecoveryEvidence.sha256 == fields["sha256"],
        )
    )
    if prior:
        if prior.case_id != case.id:
            raise DomainError("DUPLICATE_CREDIT", "This evidence already belongs to another case.")
        return prior, case, False
    if (
        session.scalar(
            select(func.count())
            .select_from(RecoveryEvidence)
            .where(RecoveryEvidence.case_id == case.id)
        )
        >= 50
    ):
        raise DomainError("TRACKING_LIMIT", "Maximum evidence count reached.", 429)
    consume(session, owner, "uploads", settings.daily_uploads)
    evidence = RecoveryEvidence(id=uuid4(), case_id=case.id, owner_id=owner, **fields)
    session.add(evidence)
    change(
        session,
        case,
        "credit_evidence_attached",
        actor=owner,
        metadata={"evidence_id": str(evidence.id)},
    )
    return evidence, case, True
