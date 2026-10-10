"""Explicit local or hosted configuration; hosted mode has no identity fallback."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.engine import make_url

SCHEMA_VERSION = "0003_phase5"


def origin_url(value, *, https=False):
    url = urlparse(value)
    if (
        url.scheme not in (("https",) if https else ("http",))
        or not url.hostname
        or url.path
        or url.query
        or url.fragment
        or url.username
        or url.password
    ):
        raise RuntimeError("Expected an origin without a path, credentials or query.")
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    storage_root: Path
    local_owner: UUID | None
    mode: str = "local"
    lease_seconds: int = 120
    model: str = ""
    web_origin: str = "http://127.0.0.1:3000"
    api_origin: str = ""
    supabase_url: str = ""
    supabase_secret_key: str = field(default="", repr=False)
    storage_bucket: str = "avoirly-documents"
    metrics_token: str = field(default="", repr=False)
    daily_cases: int = 20
    daily_analyses: int = 40
    daily_uploads: int = 60
    daily_reviews: int = 120
    daily_tracking: int = 120
    max_attempts: int = 3
    pilot_owner_ids: tuple[UUID, ...] = ()
    input_usd_per_million: str = ""
    output_usd_per_million: str = ""

    @property
    def hosted(self):
        return self.mode == "hosted"

    def validate(self):
        if self.mode not in ("local", "hosted"):
            raise RuntimeError("Select explicit local or hosted mode.")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise RuntimeError("A PostgreSQL psycopg connection is required.")
        if self.lease_seconds < 10:
            raise RuntimeError("Lease must be at least 10 seconds.")
        if (
            min(
                self.daily_cases,
                self.daily_analyses,
                self.daily_uploads,
                self.daily_reviews,
                self.daily_tracking,
                self.max_attempts,
            )
            < 1
        ):
            raise RuntimeError("Quotas and maximum attempts must be positive.")
        origin = origin_url(self.web_origin, https=self.hosted)
        if not self.hosted:
            if origin.hostname not in ("localhost", "127.0.0.1", "::1") or self.local_owner is None:
                raise RuntimeError(
                    "Local mode requires a loopback web origin and explicit identity."
                )
            return
        if self.local_owner is not None:
            raise RuntimeError("Hosted mode must not configure a developer identity.")
        if make_url(self.database_url).query.get("sslmode") not in (
            "require",
            "verify-ca",
            "verify-full",
        ):
            raise RuntimeError("Hosted PostgreSQL requires TLS (sslmode=require or stronger).")
        origin_url(self.api_origin, https=True)
        project = origin_url(self.supabase_url, https=True)
        if not re.fullmatch(r"[a-z0-9-]+\.supabase\.co", project.hostname or ""):
            raise RuntimeError("Configure the managed Supabase project HTTPS origin.")
        if not self.supabase_secret_key.startswith("sb_secret_"):
            raise RuntimeError("Configure a server-only Supabase secret API key.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", self.storage_bucket):
            raise RuntimeError("Invalid private bucket name.")
        if len(self.metrics_token) < 32 or not self.pilot_owner_ids:
            raise RuntimeError(
                "Hosted mode requires a metrics token and an explicit pilot user allowlist."
            )

    @classmethod
    def from_env(cls):
        owner = os.environ.get("AVOIRLY_LOCAL_OWNER_ID", "")
        settings = cls(
            database_url=os.environ["DATABASE_URL"],
            storage_root=Path(os.environ.get("AVOIRLY_STORAGE_ROOT", ".private")).resolve(),
            local_owner=UUID(owner) if owner else None,
            mode=os.environ.get("AVOIRLY_MODE", "disabled"),
            lease_seconds=int(os.environ.get("AVOIRLY_LEASE_SECONDS", "120")),
            model=os.environ.get("OPENAI_MODEL", "").strip(),
            web_origin=os.environ.get("AVOIRLY_WEB_ORIGIN", "http://127.0.0.1:3000"),
            api_origin=os.environ.get("AVOIRLY_API_ORIGIN", ""),
            supabase_url=os.environ.get("SUPABASE_URL", ""),
            supabase_secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
            storage_bucket=os.environ.get("AVOIRLY_STORAGE_BUCKET", "avoirly-documents"),
            metrics_token=os.environ.get("AVOIRLY_METRICS_TOKEN", ""),
            daily_cases=int(os.environ.get("AVOIRLY_DAILY_CASES", "20")),
            daily_analyses=int(os.environ.get("AVOIRLY_DAILY_ANALYSES", "40")),
            daily_uploads=int(os.environ.get("AVOIRLY_DAILY_UPLOADS", "60")),
            daily_reviews=int(os.environ.get("AVOIRLY_DAILY_REVIEWS", "120")),
            daily_tracking=int(os.environ.get("AVOIRLY_DAILY_TRACKING", "120")),
            max_attempts=int(os.environ.get("AVOIRLY_MAX_ATTEMPTS", "3")),
            pilot_owner_ids=tuple(
                UUID(v.strip())
                for v in os.environ.get("AVOIRLY_PILOT_OWNER_IDS", "").split(",")
                if v.strip()
            ),
            input_usd_per_million=os.environ.get("AVOIRLY_INPUT_USD_PER_MILLION", ""),
            output_usd_per_million=os.environ.get("AVOIRLY_OUTPUT_USD_PER_MILLION", ""),
        )
        settings.validate()
        return settings
