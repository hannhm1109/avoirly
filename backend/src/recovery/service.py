"""Transaction boundaries for API mutations; no arbitrary status setter is exposed."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select, text, update

from .api.errors import DomainError
from .db.models import (
    Case,
    CaseEvent,
    Comparison,
    Confirmation,
    DeletionTask,
    Document,
    Draft,
    Extraction,
    IdempotencyKey,
    Job,
    RecoveryEvidence,
    utcnow,
)
from .matching import match_lines
from .models import PairConfirmation
from .quotas import consume
from .validation import revision_hash, validate_pair
from .workflow import ALLOWED_TRANSITIONS, CaseStatus


def owner_lock(session, owner):
    # Stable signed 64-bit advisory key; collisions only serialize unrelated owners.
    lock_id = int.from_bytes(hashlib.sha256(owner.bytes).digest()[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def owned_case(session, owner, case_id, expected=None, lock=False):
    query = select(Case).where(Case.id == case_id, Case.owner_id == owner)
    if lock:
        query = query.with_for_update()
    case = session.scalar(query)
    if case is None:
        raise DomainError("NOT_FOUND", "Case not found.", 404)
    if expected is not None and case.version != expected:
        raise DomainError("VERSION_CONFLICT", "Case changed; reload before retrying.")
    return case


def change(session, case, event, *, actor=None, target=None, metadata=None, **values):
    old = case.status
    if target is not None:
        legal = ALLOWED_TRANSITIONS[CaseStatus(old)].get(event)
        if legal is None or legal.value != target:
            raise DomainError("ILLEGAL_TRANSITION", f"Cannot {event} a case in {old}.")
    target = target or old
    if old == "CLOSED":
        raise DomainError("CASE_CLOSED", "Closed cases cannot be changed.")
    version, revision = case.version, case.current_revision
    result = session.execute(
        update(Case)
        .where(
            Case.id == case.id,
            Case.owner_id == case.owner_id,
            Case.status == old,
            Case.version == version,
            Case.current_revision == revision,
        )
        .values(status=target, version=version + 1, updated_at=utcnow(), **values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise DomainError("VERSION_CONFLICT", "Concurrent case change.")
    session.add(
        CaseEvent(
            case_id=case.id,
            owner_id=case.owner_id,
            actor_id=actor,
            event=event,
            old_status=old,
            new_status=target,
            revision=values.get("current_revision", revision),
            metadata_json=metadata or {},
        )
    )
    session.refresh(case)


def current_documents(session, case):
    return {
        d.role: d
        for d in session.scalars(
            select(Document).where(
                Document.case_id == case.id, Document.revision == case.current_revision
            )
        )
    }


def latest_extraction(session, document):
    return session.scalar(
        select(Extraction)
        .where(Extraction.document_id == document.id)
        .order_by(Extraction.version.desc())
        .limit(1)
    )


def new_document_revision(
    session, case, revision, *, replacement=None, corrected=None, actor=None, reason=None
):
    old_documents = current_documents(session, case)
    created = {}
    for role in ("PO", "INVOICE"):
        old = old_documents.get(role)
        replacement_here = replacement and replacement["role"] == role
        if old is None and not replacement_here:
            continue
        fields = (
            {
                name: getattr(old, name)
                for name in (
                    "role",
                    "storage_key",
                    "original_name",
                    "mime_type",
                    "size_bytes",
                    "sha256",
                    "page_count",
                )
            }
            if old
            else {}
        )
        if replacement_here:
            fields = replacement
        doc = Document(
            id=uuid4(), case_id=case.id, owner_id=case.owner_id, revision=revision, **fields
        )
        session.add(doc)
        session.flush()
        created[role] = doc
        prior = latest_extraction(session, old) if old else None
        if not replacement_here and (prior or corrected):
            data = (
                (corrected.purchase_order if role == "PO" else corrected.invoice)
                if corrected
                else None
            )
            # Preserve the exact original provider snapshot even through many human revisions.
            session.add(
                Extraction(
                    document_id=doc.id,
                    version=1,
                    raw_json=prior.raw_json if prior else {},
                    corrected_json=data.model_dump(mode="json")
                    if corrected
                    else prior.corrected_json,
                    model=prior.model if prior else "human",
                    input_hash=doc.sha256,
                    prompt_version=prior.prompt_version if prior else "human",
                    schema_version=prior.schema_version if prior else "1",
                    request_id=prior.request_id if prior else None,
                    token_usage=prior.token_usage if prior else None,
                    duration_ms=prior.duration_ms if prior else None,
                    corrected_by=actor if corrected else prior.corrected_by,
                    correction_reason=reason if corrected else prior.correction_reason,
                )
            )
    return created


def invalidate(session, case, actor, revision, metadata):
    if case.status in ("CLAIM_SENT", "AWAITING_RESPONSE", "CREDIT_PROMISED", "CREDIT_CONFIRMED"):
        raise DomainError("CLAIM_FROZEN", "Correct the sent record before changing claim inputs.")
    if case.status == "PROCESSING":
        raise DomainError(
            "CASE_PROCESSING", "Wait for processing or explicitly recover an expired job."
        )
    if case.status == "CLOSED":
        raise DomainError("CASE_CLOSED", "Closed cases cannot be changed.")
    session.execute(
        update(Job)
        .where(Job.case_id == case.id, Job.status.in_(["QUEUED", "RUNNING"]))
        .values(status="FAILED", error_code="INPUT_CHANGED", lease_token=None)
    )
    event = (
        "inputs_changed"
        if case.status == "PENDING"
        else "retry"
        if case.status == "FAILED"
        else "revise"
    )
    change(
        session,
        case,
        event,
        actor=actor,
        target=None if case.status == "PENDING" else "PENDING",
        current_revision=revision,
        processing_step=None,
        currency=None,
        potential_credit_net=None,
        error_code=None,
        close_reason=None,
        metadata=metadata,
    )


def attach_document(session, owner, case_id, expected, fields):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, expected, lock=True)
    if case.status in ("CLAIM_SENT", "AWAITING_RESPONSE", "CREDIT_PROMISED", "CREDIT_CONFIRMED"):
        raise DomainError("CLAIM_FROZEN", "Sent claim documents are preserved for tracking.")
    # Same source in the same role is a harmless upload retry, but never in both roles.
    current = current_documents(session, case)
    same = current.get(fields["role"])
    if same and same.sha256 == fields["sha256"]:
        if case.status == "CLOSED":
            raise DomainError("CASE_CLOSED", "Closed cases cannot be changed.")
        return same, case, False
    duplicate = session.scalar(
        select(Document)
        .where(
            Document.owner_id == owner,
            Document.sha256 == fields["sha256"],
            (Document.case_id != case.id) | (Document.role != fields["role"]),
        )
        .limit(1)
    )
    if duplicate:
        raise DomainError(
            "DUPLICATE_FILE",
            "This file is already attached to a case.",
            details={"existing_case_id": str(duplicate.case_id)},
        )
    revision = case.current_revision + 1
    docs = new_document_revision(session, case, revision, replacement=fields)
    invalidate(session, case, owner, revision, {"role": fields["role"]})
    return docs[fields["role"]], case, True


def save_review(session, owner, case_id, request):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, request.expected_version, lock=True)
    if case.status in ("CLAIM_SENT", "AWAITING_RESPONSE", "CREDIT_PROMISED", "CREDIT_CONFIRMED"):
        raise DomainError("CLAIM_FROZEN", "Sent claim inputs are preserved for tracking.")
    if not request.reason.strip():
        raise DomainError("INVALID_REASON", "A correction reason is required.", 422)
    docs = current_documents(session, case)
    if set(docs) != {"PO", "INVOICE"}:
        raise DomainError("MISSING_DOCUMENTS", "Upload both documents before review.", 422)
    pages = {k: d.page_count for k, d in docs.items()}
    confirmation = (
        PairConfirmation(
            actor=str(owner), reason=request.reason, revision_hash=revision_hash(request.corrected)
        )
        if request.confirm_pair
        else None
    )
    validation = validate_pair(request.corrected, confirmation, page_counts=pages)
    # Human mappings are assertions to verify, never a bypass for uniqueness/unit/SKU rules.
    if request.mappings:
        matches = match_lines(validation) if not isinstance(validation, list) else validation
        declared = {(m.po_line_number, m.invoice_line_number) for m in request.mappings}
        if (
            isinstance(matches, list)
            or len(declared) != len(request.mappings)
            or declared != {(p.line_number, i.line_number) for p, i in matches.lines}
        ):
            raise DomainError(
                "UNSUPPORTED_MAPPING",
                "Correct the extracted keys first; mappings must satisfy every matching rule.",
                422,
            )
    revision = case.current_revision + 1
    new_document_revision(
        session, case, revision, corrected=request.corrected, actor=owner, reason=request.reason
    )
    invalidate(session, case, owner, revision, {"reason": request.reason})
    for kind, value in (
        ("PAIR", confirmation.model_dump() if confirmation else None),
        ("MAPPINGS", [m.model_dump() for m in request.mappings] or None),
    ):
        if value:
            session.add(
                Confirmation(
                    case_id=case.id,
                    revision=revision,
                    kind=kind,
                    value_json={"value": value},
                    actor_id=owner,
                    reason=request.reason,
                )
            )
    return case


def enqueue(session, owner, case_id, request, key, model, *, retry=False, settings=None):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, lock=True)
    route = f"/cases/{case_id}/{'retry' if retry else 'analyze'}"
    digest = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()
    previous = session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.owner_id == owner,
            IdempotencyKey.route == route,
            IdempotencyKey.key == key,
        )
    )
    now = session.scalar(select(func.clock_timestamp()))
    if previous and previous.expires_at > now:
        if previous.request_hash != digest:
            raise DomainError("IDEMPOTENCY_CONFLICT", "This key was used with a different payload.")
        return previous.response
    if previous:
        session.delete(previous)
        session.flush()
    if case.version != request.expected_version:
        raise DomainError("VERSION_CONFLICT", "Case changed; reload before retrying.")
    if not model:
        docs = current_documents(session, case)
        reviewed = [latest_extraction(session, doc) for doc in docs.values()]
        if set(docs) != {"PO", "INVOICE"} or not all(
            ext
            and ext.corrected_json is not None
            and ext.corrected_by
            and ext.input_hash == doc.sha256
            for doc, ext in zip(docs.values(), reviewed, strict=True)
        ):
            raise DomainError("MISSING_MODEL", "Configure OPENAI_MODEL before extraction.", 422)
        # Both current inputs have audited human values. No provider call is needed;
        # the worker still applies every validation, matching and duplicate check.
        model = "human-reviewed"
    if retry and case.status != "FAILED":
        raise DomainError("ILLEGAL_RETRY", "Only failed cases can be retried.")
    active = session.scalar(
        select(Job).where(
            Job.case_id == case.id,
            Job.revision == case.current_revision,
            Job.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    if active:
        response = {"job_id": str(active.id), "case_id": str(case.id), "version": case.version}
    else:
        if case.status not in (("FAILED",) if retry else ("PENDING",)):
            raise DomainError(
                "ILLEGAL_ANALYZE", "Create a corrected revision or retry a failed case."
            )
        docs = current_documents(session, case)
        if set(docs) != {"PO", "INVOICE"}:
            raise DomainError(
                "MISSING_DOCUMENTS", "Upload one purchase order and one invoice.", 422
            )
        if session.scalar(
            select(Job.id)
            .where(Job.owner_id == owner, Job.status.in_(["QUEUED", "RUNNING"]))
            .limit(1)
        ):
            raise DomainError("OWNER_BUSY", "One processing job per user is allowed.", 429)
        if retry:
            change(session, case, "retry", actor=owner, target="PENDING", error_code=None)
        attempt = (
            session.scalar(
                select(func.max(Job.attempt)).where(
                    Job.case_id == case.id, Job.revision == case.current_revision
                )
            )
            or 0
        ) + 1
        if attempt > (settings.max_attempts if settings else 3):
            raise DomainError("RETRY_LIMIT", "Maximum attempts reached for this revision.", 429)
        consume(session, owner, "analyses", settings.daily_analyses if settings else 40)
        job = Job(
            id=uuid4(),
            case_id=case.id,
            owner_id=owner,
            revision=case.current_revision,
            attempt=attempt,
            language=request.language,
            model=model,
        )
        session.add(job)
        change(session, case, "job_queued", actor=owner, processing_step="QUEUED")
        response = {"job_id": str(job.id), "case_id": str(case.id), "version": case.version}
    session.add(
        IdempotencyKey(
            owner_id=owner,
            case_id=case.id,
            route=route,
            key=key,
            request_hash=digest,
            response=response,
            expires_at=now + timedelta(days=1),
        )
    )
    return response


def current_comparison(session, case):
    return session.scalar(
        select(Comparison).where(
            Comparison.case_id == case.id,
            Comparison.revision == case.current_revision,
            Comparison.engine_version == "1",
        )
    )


def current_draft(session, case):
    comparison = current_comparison(session, case)
    if not comparison or case.status != "CLAIM_DRAFTED":
        return None
    return session.scalar(
        select(Draft)
        .where(Draft.comparison_id == comparison.id)
        .order_by(Draft.version.desc())
        .limit(1)
    )


def edit_draft(session, owner, case_id, request):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, request.expected_version, lock=True)
    prior = current_draft(session, case)
    if not prior:
        raise DomainError("NO_CURRENT_DRAFT", "There is no current draft to edit.")
    if (
        not request.subject.strip()
        or not request.body.strip()
        or any(c in request.subject for c in "\r\n")
    ):
        raise DomainError(
            "INVALID_DRAFT", "Provide a subject on one line and a nonempty body.", 422
        )
    draft = Draft(
        case_id=case.id,
        comparison_id=prior.comparison_id,
        version=prior.version + 1,
        subject=request.subject,
        body=request.body,
        language=prior.language,
        edited_by=owner,
    )
    session.add(draft)
    change(session, case, "draft_edited", actor=owner, metadata={"draft_version": draft.version})
    return case


def close_case(session, owner, case_id, request):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, request.expected_version, lock=True)
    change(session, case, "close", actor=owner, target="CLOSED", close_reason=request.close_reason)
    session.execute(
        update(Job)
        .where(Job.case_id == case.id, Job.status.in_(["QUEUED", "RUNNING"]))
        .values(status="FAILED", error_code="CASE_CLOSED", lease_token=None)
    )
    return case


def delete_case(session, owner, case_id, expected):
    owner_lock(session, owner)
    case = owned_case(session, owner, case_id, expected, lock=True)
    keys = set(session.scalars(select(Document.storage_key).where(Document.case_id == case.id)))
    keys.update(
        session.scalars(
            select(RecoveryEvidence.storage_key).where(RecoveryEvidence.case_id == case.id)
        )
    )
    for key in keys:
        session.add(DeletionTask(storage_key=key))
    # FK cascade removes content, jobs and leases atomically, preventing a later worker commit.
    session.delete(case)


def cleanup_deleted(sessions, storage):
    with sessions.begin() as session:
        for task in session.scalars(select(DeletionTask).with_for_update(skip_locked=True)):
            storage.delete(task.storage_key)
            session.delete(task)


def case_summary(case):
    return {
        "id": str(case.id),
        "status": case.status,
        "version": case.version,
        "current_revision": case.current_revision,
        "processing_step": case.processing_step,
        "currency": case.currency,
        "potential_credit_net": str(case.potential_credit_net)
        if case.potential_credit_net is not None
        else None,
        "close_reason": case.close_reason,
        "error_code": case.error_code,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


def case_detail(session, case, *, recovery_history=True):
    from .tracking import detail as recovery_detail
    from .tracking import summary as recovery_summary

    data = case_summary(case)
    comparison = current_comparison(session, case)
    draft = current_draft(session, case)
    docs = current_documents(session, case)
    data["documents"] = {
        role: {
            "id": str(d.id),
            "original_name": d.original_name,
            "mime_type": d.mime_type,
            "page_count": d.page_count,
        }
        for role, d in docs.items()
    }
    data["extractions"] = {}
    for role, doc in docs.items():
        ext = latest_extraction(session, doc)
        if ext:
            data["extractions"][role] = {
                "id": str(ext.id),
                "version": ext.version,
                "raw": ext.raw_json,
                "corrected": ext.corrected_json,
            }
    data["comparison"] = comparison.result_json if comparison else None
    data["review_issues"] = comparison.result_json["review_issues"] if comparison else []
    data["draft"] = (
        {
            "id": str(draft.id),
            "version": draft.version,
            "subject": draft.subject,
            "body": draft.body,
            "language": draft.language,
        }
        if draft
        else None
    )
    data["jobs"] = [
        {
            "id": str(j.id),
            "status": j.status,
            "attempt": j.attempt,
            "revision": j.revision,
            "error_code": j.error_code,
        }
        for j in session.scalars(
            select(Job).where(Job.case_id == case.id).order_by(Job.created_at.desc()).limit(20)
        )
    ]
    data["recovery"] = (
        recovery_detail(session, case) if recovery_history else recovery_summary(session, case)
    )
    return data
