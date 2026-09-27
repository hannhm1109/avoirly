"""Phase 2 runs locally only; hosted identity is a Phase 4 gate."""

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_root: Path
    local_owner: UUID
    mode: str = "local"
    lease_seconds: int = 120
    model: str = ""

    def validate(self):
        if self.mode != "local":
            raise RuntimeError(
                "Phase 2 permits explicitly local mode only. Hosted authentication is not implemented."
            )
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise RuntimeError("A PostgreSQL psycopg connection is required.")
        if self.lease_seconds < 10:
            raise RuntimeError("Lease must be at least 10 seconds.")

    @classmethod
    def from_env(cls):
        # No implicit developer identity or database credentials.
        settings = cls(
            database_url=os.environ["DATABASE_URL"],
            storage_root=Path(os.environ["AVOIRLY_STORAGE_ROOT"]).resolve(),
            local_owner=UUID(os.environ["AVOIRLY_LOCAL_OWNER_ID"]),
            mode=os.environ.get("AVOIRLY_MODE", "disabled"),
            lease_seconds=int(os.environ.get("AVOIRLY_LEASE_SECONDS", "120")),
            model=os.environ.get("OPENAI_MODEL", "").strip(),
        )
        settings.validate()
        return settings
