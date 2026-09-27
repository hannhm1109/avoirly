"""Synchronous Phase 1 workflow. Durable ownership/leases belong to Phase 2."""

from enum import StrEnum

from .claims import generate_claim
from .comparison import compare, needs_review
from .models import PairConfirmation
from .validation import revision_hash, validate_pair


class CaseStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NO_DISCREPANCY = "NO_DISCREPANCY"
    DISCREPANCY_FOUND = "DISCREPANCY_FOUND"
    CLAIM_DRAFTED = "CLAIM_DRAFTED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


ALLOWED_TRANSITIONS = {
    CaseStatus.PENDING: {"start": CaseStatus.PROCESSING},
    CaseStatus.PROCESSING: {
        "review": CaseStatus.NEEDS_REVIEW,
        "no_discrepancy": CaseStatus.NO_DISCREPANCY,
        "discrepancy": CaseStatus.DISCREPANCY_FOUND,
        "fail": CaseStatus.FAILED,
    },
    CaseStatus.DISCREPANCY_FOUND: {
        "draft_saved": CaseStatus.CLAIM_DRAFTED,
        "fail": CaseStatus.FAILED,
        "revise": CaseStatus.PENDING,
        "close": CaseStatus.CLOSED,
    },
    CaseStatus.NEEDS_REVIEW: {"revise": CaseStatus.PENDING, "close": CaseStatus.CLOSED},
    CaseStatus.NO_DISCREPANCY: {"revise": CaseStatus.PENDING, "close": CaseStatus.CLOSED},
    CaseStatus.CLAIM_DRAFTED: {"revise": CaseStatus.PENDING, "close": CaseStatus.CLOSED},
    CaseStatus.FAILED: {"retry": CaseStatus.PENDING, "close": CaseStatus.CLOSED},
    CaseStatus.CLOSED: {},
}


class Workflow:
    def __init__(self):
        self.status = CaseStatus.PENDING
        self.events = []

    def _transition(self, event):
        target = ALLOWED_TRANSITIONS[self.status].get(event)
        if target is None:
            raise ValueError(f"Illegal event {event} in {self.status}.")
        self.events.append(
            {"event": event, "old_status": self.status.value, "new_status": target.value}
        )
        self.status = target

    def start(self):
        self._transition("start")

    def comparison_completed(self, result):
        if result.outcome == "NEEDS_REVIEW":
            valid = (
                bool(result.review_issues)
                and not result.findings
                and result.potential_credit_net is None
            )
            event = "review"
        elif result.outcome == "NO_DISCREPANCY":
            valid = (
                not result.review_issues
                and not result.findings
                and result.potential_credit_net == 0
            )
            event = "no_discrepancy"
        else:
            valid = (
                bool(result.findings)
                and not result.review_issues
                and result.potential_credit_net > 0
            )
            event = "discrepancy"
        if not valid:
            raise ValueError("Comparison evidence is inconsistent.")
        self._transition(event)

    def draft_saved(self, draft):
        if not draft.subject.strip() or not draft.body.strip():
            raise ValueError("Draft evidence is required.")
        self._transition("draft_saved")

    def fail(self):
        self._transition("fail")


def analyze_extraction(
    raw, *, page_counts, language="fr", confirmation_actor=None, confirmation_reason=None
):
    workflow = Workflow()
    workflow.start()
    confirmation = None
    if confirmation_actor and confirmation_reason:
        confirmation = PairConfirmation(
            actor=confirmation_actor, reason=confirmation_reason, revision_hash=revision_hash(raw)
        )
    validated = validate_pair(raw, confirmation, page_counts=page_counts)
    result = needs_review(validated) if isinstance(validated, list) else compare(validated)
    workflow.comparison_completed(result)
    draft = None
    if result.outcome == "DISCREPANCY_FOUND":
        draft = generate_claim(validated, result, language)
        workflow.draft_saved(draft)
    return {
        "product": "Avoirly",
        "engine_version": "1",
        "status": workflow.status.value,
        "extraction": raw.model_dump(mode="json"),
        "validated_pair": None
        if isinstance(validated, list)
        else validated.model_dump(mode="json"),
        "comparison": result.model_dump(mode="json"),
        "review_issues": [i.model_dump(mode="json") for i in result.review_issues],
        "claim_draft": draft.model_dump(mode="json") if draft else None,
        "confirmations": [confirmation.model_dump()] if confirmation else [],
        "revision_hash": revision_hash(raw),
        "events": workflow.events,
    }
