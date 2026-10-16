"""Send a content-free operational alert; never mail documents or raw logs."""

import argparse
import json
import os
import smtplib
import ssl
import time
from datetime import UTC, datetime
from email.headerregistry import Address
from email.message import EmailMessage
from pathlib import Path

ALLOWED_UNITS = {
    "avoirly-backup.service",
    "avoirly-monitor.service",
    "avoirly-full-backup.service",
}


def send_alert(unit, *, test=False, environment=None, smtp_factory=None):
    env = os.environ if environment is None else environment
    if unit not in ALLOWED_UNITS:
        raise ValueError("Unknown operational service")
    sender, recipient = env["AVOIRLY_SMTP_USER"], env["AVOIRLY_ALERT_EMAIL"]
    for value in (sender, recipient):
        if (
            "\r" in value
            or "\n" in value
            or Address(addr_spec=value).addr_spec != value
        ):
            raise ValueError("Expected a single plain email address")
    password = env["AVOIRLY_SMTP_PASSWORD"]
    if not password:
        raise ValueError("Missing SMTP credential")
    state = Path(env.get("AVOIRLY_ALERT_STATE_DIR", "/var/lib/avoirly-alerts"))
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = state / (unit + ".last-sent")
    now = time.time()
    if not test and marker.exists() and now - float(marker.read_text()) < 3600:
        return {"alert_sent": False, "duplicate_suppressed": True}
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = (
        "Avoirly: test operational alert"
        if test
        else "Avoirly: operational check failed"
    )
    message.set_content(
        "This is an authorized Avoirly alert-delivery test.\n"
        if test
        else "An Avoirly operational check failed. Review the private server journal.\n"
    )
    message.set_content(
        message.get_content()
        + f"Service: {unit}\nUTC: {datetime.now(UTC).isoformat()}\nNo documents, credentials or log excerpts are included.\n"
    )
    factory = smtp_factory or smtplib.SMTP_SSL
    with factory(
        "smtp.gmail.com", 465, timeout=20, context=ssl.create_default_context()
    ) as client:
        client.login(sender, password)
        client.send_message(message)
    if not test:
        marker.write_text(str(now))
        marker.chmod(0o600)
    return {"alert_sent": True, "test": test}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit", choices=sorted(ALLOWED_UNITS))
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(send_alert(args.unit, test=args.test)))
    except Exception as exc:  # noqa: BLE001 - SMTP exceptions can contain credentials/addresses
        print(json.dumps({"operator_alert_failed": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
