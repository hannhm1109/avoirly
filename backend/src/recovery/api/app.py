"""Local-only Phase 2 API. No client-selected owner or arbitrary status mutation."""

import ipaddress
import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..auth import TokenVerifier
from ..config import SCHEMA_VERSION, Settings
from ..db.models import Case, CaseEvent, Document
from ..db.session import create_sessions
from ..extraction import MAX_BYTES, ProcessingError
from ..operations import metrics
from ..quotas import consume
from ..service import (
    attach_document,
    case_detail,
    case_summary,
    cleanup_deleted,
    close_case,
    delete_case,
    edit_draft,
    enqueue,
    owned_case,
    owner_lock,
    save_review,
)
from ..storage import create_storage
from .errors import DomainError
from .schemas import AnalyzeRequest, CloseRequest, DeleteRequest, EditDraftRequest, ReviewRequest

logger = logging.getLogger(__name__)


def get_owner(request: Request):
    if request.app.state.settings.hosted:
        return request.app.state.verifier.owner(request.headers.get("authorization"))
    return request.app.state.settings.local_owner


class LocalBoundary:
    def __init__(self, app, web_origin="http://127.0.0.1:3000", hosted=False):
        self.app = app
        self.web_origin = web_origin
        self.hosted = hosted

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid = str(uuid4())
        scope.setdefault("state", {})["request_id"] = rid
        host = (scope.get("client") or ("",))[0]
        try:
            allowed = ipaddress.ip_address(host).is_loopback
        except ValueError:
            allowed = False
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("ascii", errors="replace")
        local_origins = {
            f"http://{h}:{p}" for h in ("localhost", "127.0.0.1", "[::1]") for p in (8000, 3000)
        }
        local_origins.add(self.web_origin)
        if self.hosted:
            local_origins = {self.web_origin}

        async def error(code, message, status):
            return await JSONResponse(
                {"code": code, "message": message, "details": None, "request_id": rid},
                status_code=status,
            )(scope, receive, send)

        if not allowed and not self.hosted:
            return await error(
                "LOCAL_ONLY", "This development API accepts loopback clients only.", 403
            )
        if origin and origin not in local_origins:
            return await error("ORIGIN_FORBIDDEN", "Origin is not allowed.", 403)
        # Bound the whole body including chunked uploads before multipart spooling.
        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > MAX_BYTES + 65536:
                return await error("FILE_SIZE", "Request exceeds the upload limit.", 413)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        response_started = False

        async def safe_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                message.setdefault("headers", []).extend(
                    [
                        (b"x-request-id", rid.encode()),
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
            await send(message)

        try:
            await self.app(scope, replay, safe_send)
        except Exception as exc:  # noqa: BLE001 - prevent server traceback logs from leaking SQL/document values
            logger.error("request_failed request_id=%s type=%s", rid, type(exc).__name__)
            if not response_started:
                await error("INTERNAL_ERROR", "Request failed; retry with the request ID.", 500)


def create_app(settings=None, sessions=None, *, storage=None, verifier=None):
    settings = settings or Settings.from_env()
    settings.validate()
    engine = None
    if sessions is None:
        engine, sessions = create_sessions(settings.database_url)
    storage = storage or create_storage(settings)

    @asynccontextmanager
    async def lifespan(app):
        # Fail early if an explicit migration was not applied; no create_all on startup.
        with sessions() as session:
            if session.scalar(text("SELECT version_num FROM alembic_version")) != SCHEMA_VERSION:
                raise RuntimeError("Run Alembic upgrade head before starting the API.")
        storage.check_private()
        yield
        if engine:
            engine.dispose()

    app = FastAPI(
        title="Avoirly",
        description="Spot invoice discrepancies. Simplify supplier claims.",
        version="0.4.0",
        docs_url=None if settings.hosted else "/docs",
        redoc_url=None if settings.hosted else "/redoc",
        openapi_url=None if settings.hosted else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings, app.state.sessions, app.state.storage = settings, sessions, storage
    app.state.verifier = verifier or (TokenVerifier(settings) if settings.hosted else None)
    hosts = (
        [urlparse(settings.api_origin).hostname]
        if settings.hosted
        else ["localhost", "127.0.0.1", "[::1]"]
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        allow_credentials=False,
    )
    app.add_middleware(LocalBoundary, web_origin=settings.web_origin, hosted=settings.hosted)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(
            {
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
                "request_id": request.state.request_id,
            },
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "code": "INVALID_INPUT",
                "message": "Request validation failed.",
                "details": [{"field": list(e["loc"]), "message": e["msg"]} for e in exc.errors()],
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        codes = {
            400: "INVALID_REQUEST",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            413: "FILE_SIZE",
        }
        return JSONResponse(
            {
                "code": codes.get(exc.status_code, "HTTP_ERROR"),
                "message": str(exc.detail),
                "details": None,
                "request_id": request.state.request_id,
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        # Never log SQL parameters, document content, provider errors or secrets.
        logger.error(
            "request_failed request_id=%s type=%s", request.state.request_id, type(exc).__name__
        )
        return JSONResponse(
            {
                "code": "INTERNAL_ERROR",
                "message": "Request failed; retry with the request ID.",
                "details": None,
                "request_id": request.state.request_id,
            },
            status_code=500,
        )

    owner_dep = Annotated[UUID, Depends(get_owner)]
    prefix = "/api/v1"

    @app.get(prefix + "/health")
    def health():
        with sessions() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "mode": settings.mode, "product": "Avoirly"}

    @app.get("/ops/metrics")
    def operations(request: Request):
        import secrets

        supplied = request.headers.get("authorization", "")
        if not settings.metrics_token or not secrets.compare_digest(
            supplied.encode(), ("Bearer " + settings.metrics_token).encode()
        ):
            raise DomainError("UNAUTHENTICATED", "Operator authentication required.", 401)
        return metrics(sessions)

    @app.post(prefix + "/cases", status_code=201)
    def create_case(owner: owner_dep):
        with sessions.begin() as session:
            owner_lock(session, owner)
            consume(session, owner, "cases", settings.daily_cases)
            case = Case(id=uuid4(), owner_id=owner)
            session.add(case)
            session.flush()
            session.add(
                CaseEvent(
                    case_id=case.id,
                    owner_id=owner,
                    actor_id=owner,
                    event="created",
                    old_status="PENDING",
                    new_status="PENDING",
                    revision=0,
                    metadata_json={},
                )
            )
            return case_summary(case)

    @app.get(prefix + "/cases")
    def list_cases(
        owner: owner_dep, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with sessions() as session:
            cases = session.scalars(
                select(Case)
                .where(Case.owner_id == owner)
                .order_by(Case.created_at.desc(), Case.id.desc())
                .offset(offset)
                .limit(limit)
            )
            items, totals = [], {}
            for case in cases:
                detail = case_detail(session, case)
                item = case_summary(case)
                values = {
                    role: ext["corrected"] or ext["raw"]
                    for role, ext in detail["extractions"].items()
                }
                invoice, po = values.get("INVOICE", {}), values.get("PO", {})
                item.update(
                    supplier_name=(invoice.get("supplier") or {}).get("name"),
                    invoice_number=invoice.get("document_number"),
                    po_number=po.get("document_number"),
                )
                items.append(item)
                if (
                    case.status in ("DISCREPANCY_FOUND", "CLAIM_DRAFTED", "NO_DISCREPANCY")
                    and case.currency
                    and case.potential_credit_net is not None
                ):
                    totals[case.currency] = (
                        totals.get(case.currency, Decimal(0)) + case.potential_credit_net
                    )
            return {
                "items": items,
                "limit": limit,
                "offset": offset,
                "potential_credit_by_currency": {k: str(v) for k, v in totals.items()},
            }

    @app.get(prefix + "/cases/{case_id}")
    def get_case(case_id: UUID, owner: owner_dep):
        with sessions() as session:
            return case_detail(session, owned_case(session, owner, case_id))

    @app.get(prefix + "/cases/{case_id}/events")
    def events(
        case_id: UUID,
        owner: owner_dep,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with sessions() as session:
            owned_case(session, owner, case_id)
            rows = session.scalars(
                select(CaseEvent)
                .where(CaseEvent.case_id == case_id)
                .order_by(CaseEvent.created_at, CaseEvent.id)
                .offset(offset)
                .limit(limit)
            )
            return {
                "items": [
                    {
                        "event": r.event,
                        "actor_id": str(r.actor_id) if r.actor_id else None,
                        "old_status": r.old_status,
                        "new_status": r.new_status,
                        "revision": r.revision,
                        "metadata": r.metadata_json,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rows
                ]
            }

    @app.post(prefix + "/cases/{case_id}/documents", status_code=201)
    def upload(
        case_id: UUID,
        owner: owner_dep,
        role: Annotated[Literal["PO", "INVOICE"], Form()],
        expected_version: Annotated[int, Form(ge=1)],
        file: Annotated[UploadFile, File()],
    ):
        with sessions() as session:
            owned_case(session, owner, case_id, expected_version)
        storage_key = None
        keep = False
        try:
            storage_key, checked = storage.save_upload(file.file, file.filename)
            fields = dict(
                role=role,
                storage_key=storage_key,
                original_name=(file.filename or "document").replace("\\", "/").split("/")[-1][:255],
                **checked.metadata(),
            )
            with sessions.begin() as session:
                owner_lock(session, owner)
                consume(session, owner, "uploads", settings.daily_uploads)
                doc, case, keep = attach_document(session, owner, case_id, expected_version, fields)
                result = {"document_id": str(doc.id), **case_summary(case)}
            return result
        except ProcessingError as exc:
            status = (
                413
                if exc.code in ("FILE_SIZE", "PIXEL_LIMIT", "PAGE_LIMIT")
                else 415
                if exc.code == "WRONG_MIME"
                else 422
            )
            raise DomainError(exc.code, str(exc), status) from exc
        except Exception:
            keep = False
            raise
        finally:
            file.file.close()
            if storage_key and not keep:
                storage.delete(storage_key)

    @app.get(prefix + "/documents/{document_id}/content")
    def content(document_id: UUID, owner: owner_dep):
        with sessions() as session:
            doc = session.scalar(
                select(Document).where(Document.id == document_id, Document.owner_id == owner)
            )
            if not doc:
                raise DomainError("NOT_FOUND", "Document not found.", 404)
            try:
                data = storage.read(doc.storage_key)
            except FileNotFoundError as exc:
                raise DomainError("NOT_FOUND", "Document not found.", 404) from exc
            return Response(
                data,
                media_type=doc.mime_type,
                headers={
                    "Content-Disposition": f'inline; filename="document.{doc.storage_key.rsplit(".", 1)[-1]}"',
                    "Content-Security-Policy": "sandbox",
                },
            )

    @app.post(prefix + "/cases/{case_id}/analyze", status_code=202)
    def analyze(
        case_id: UUID,
        payload: AnalyzeRequest,
        owner: owner_dep,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ):
        with sessions.begin() as session:
            return enqueue(
                session, owner, case_id, payload, idempotency_key, settings.model, settings=settings
            )

    @app.post(prefix + "/cases/{case_id}/retry", status_code=202)
    def retry(
        case_id: UUID,
        payload: AnalyzeRequest,
        owner: owner_dep,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ):
        with sessions.begin() as session:
            return enqueue(
                session,
                owner,
                case_id,
                payload,
                idempotency_key,
                settings.model,
                retry=True,
                settings=settings,
            )

    @app.put(prefix + "/cases/{case_id}/review")
    def review(case_id: UUID, payload: ReviewRequest, owner: owner_dep):
        with sessions.begin() as session:
            owner_lock(session, owner)
            consume(session, owner, "reviews", settings.daily_reviews)
            return case_summary(save_review(session, owner, case_id, payload))

    @app.patch(prefix + "/cases/{case_id}/draft")
    def draft(case_id: UUID, payload: EditDraftRequest, owner: owner_dep):
        with sessions.begin() as session:
            return case_summary(edit_draft(session, owner, case_id, payload))

    @app.post(prefix + "/cases/{case_id}/close")
    def close(case_id: UUID, payload: CloseRequest, owner: owner_dep):
        with sessions.begin() as session:
            return case_summary(close_case(session, owner, case_id, payload))

    @app.delete(prefix + "/cases/{case_id}", status_code=202)
    def remove(case_id: UUID, payload: DeleteRequest, owner: owner_dep):
        with sessions.begin() as session:
            delete_case(session, owner, case_id, payload.expected_version)
        # Source cleanup is durable even if storage is briefly unavailable.
        try:
            cleanup_deleted(sessions, storage)
        except OSError:
            pass
        return {"status": "deleted", "content_access_revoked": True}

    return app


def main():
    import uvicorn

    uvicorn.run(
        "recovery.api.app:create_app",
        factory=True,
        host="0.0.0.0" if Settings.from_env().hosted else "127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
