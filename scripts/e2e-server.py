"""Disposable browser-test API: real PostgreSQL/worker, synthetic extraction only.

Never used by the normal application launcher. No OpenAI calls, no user schema.
"""

import json
import os
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from recovery.api.app import create_app
from recovery.config import Settings
from recovery.models import Invoice, PurchaseOrder
from recovery.worker import Worker
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]


class FixtureExtractor:
    def __init__(self):
        self.metadata = []

    def extract(self, file, role):
        pair = json.loads((ROOT / "samples/pair.json").read_text(encoding="utf-8"))[
            "extraction"
        ]
        # Force the browser to resolve a real blocker before any draft can exist.
        pair["invoice"]["line_items"][0]["quantity"] = None
        return (
            PurchaseOrder.model_validate(pair["purchase_order"])
            if role == "PO"
            else Invoice.model_validate(pair["invoice"])
        )


def main():
    url = os.environ["AVOIRLY_TEST_DATABASE_URL"]
    admin = create_engine(url)
    schema = "avoirly_browser_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_url = make_url(url).update_query_dict({"options": "-csearch_path=" + schema})
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        test_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    engine = create_engine(test_url, pool_pre_ping=True)
    stop = threading.Event()
    try:
        command.upgrade(config, "head")
        with tempfile.TemporaryDirectory(prefix="avoirly-browser-") as private:
            settings = Settings(
                test_url.render_as_string(hide_password=False),
                Path(private),
                uuid4(),
                model="browser-fixture-only",
                web_origin="http://127.0.0.1:3001",
            )
            sessions = sessionmaker(engine, expire_on_commit=False)
            app = create_app(settings, sessions)
            original_lifespan = app.router.lifespan_context
            worker = Worker(
                settings, sessions, extractor_factory=lambda model: FixtureExtractor()
            )

            def consume():
                while not stop.wait(0.2):
                    worker.run_once()

            @asynccontextmanager
            async def lifespan(app):
                async with original_lifespan(app):
                    thread = threading.Thread(target=consume, daemon=True)
                    thread.start()
                    try:
                        yield
                    finally:
                        stop.set()
                        thread.join(timeout=10)

            app.router.lifespan_context = lifespan
            uvicorn.run(
                app, host="127.0.0.1", port=8001, proxy_headers=False, access_log=False
            )
    finally:
        stop.set()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
