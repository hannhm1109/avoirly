"""Operator preflight. Prints only gate names/statuses, never credentials or content."""

import json
import os

import httpx
from sqlalchemy import text

from .config import SCHEMA_VERSION, Settings
from .db.session import create_sessions
from .operations import metrics
from .storage import create_storage


def main():
    results = {}
    try:
        settings = Settings.from_env()
        results["hosted_configuration"] = settings.hosted
        engine, sessions = create_sessions(settings.database_url)
        try:
            with sessions() as session:
                results["schema_current"] = (
                    session.scalar(text("SELECT version_num FROM alembic_version"))
                    == SCHEMA_VERSION
                )
            storage = create_storage(settings)
            storage.check_private()
            results["private_storage"] = True
            if settings.hosted:
                response = httpx.get(
                    settings.supabase_url + "/auth/v1/.well-known/jwks.json", timeout=10
                )
                response.raise_for_status()
                results["asymmetric_signing_keys"] = any(
                    k.get("kty") in ("EC", "RSA") for k in response.json().get("keys", [])
                )
            state = metrics(sessions)
            results["worker_healthy"] = state["worker_healthy"]
            results["no_expired_leases"] = state["expired_leases"] == 0
            results["no_pending_file_deletions"] = state["pending_file_deletions"] == 0
            results["model_selected"] = bool(settings.model)
            results["reported_usage_priced"] = all(
                x["unpriced_records"] == 0 for x in state["reported_usage_24h"]
            )
            # This is a configuration check, not an assertion that extraction succeeded.
            results["provider_key_in_this_process"] = bool(os.environ.get("OPENAI_API_KEY"))
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001 - do not echo provider, SQL or credential details
        results["configuration_or_connectivity_error"] = type(exc).__name__
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if results and all(v is True for v in results.values()) else 1)


if __name__ == "__main__":
    main()
