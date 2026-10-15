import importlib.util
from pathlib import Path
from typing import ClassVar

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/notify-operator.py"
SPEC = importlib.util.spec_from_file_location("avoirly_notify_operator", SCRIPT)
notifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notifier)


class FakeSMTP:
    messages: ClassVar[list] = []
    fail = False

    def __init__(self, host, port, **kwargs):
        assert (host, port) == ("smtp.gmail.com", 465)
        assert kwargs["context"].check_hostname

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def login(self, *_):
        if self.fail:
            raise RuntimeError("Synthetic authentication failure")

    def send_message(self, message):
        self.messages.append(message)


@pytest.fixture
def env(tmp_path):
    FakeSMTP.messages = []
    FakeSMTP.fail = False
    return {
        "AVOIRLY_SMTP_USER": "operator@example.test",
        "AVOIRLY_ALERT_EMAIL": "recipient@example.test",
        "AVOIRLY_SMTP_PASSWORD": "synthetic-only-secret",
        "AVOIRLY_ALERT_STATE_DIR": str(tmp_path),
    }


def test_alert_uses_tls_and_excludes_secrets(env):
    result = notifier.send_alert("avoirly-monitor.service", environment=env, smtp_factory=FakeSMTP)
    assert result["alert_sent"]
    message = FakeSMTP.messages[0]
    assert str(message["To"]) == "recipient@example.test"
    assert "avoirly-monitor.service" in message.get_content()
    assert env["AVOIRLY_SMTP_PASSWORD"] not in message.as_string()
    assert not message.is_multipart()


def test_repeated_failures_are_coalesced(env):
    notifier.send_alert("avoirly-backup.service", environment=env, smtp_factory=FakeSMTP)
    result = notifier.send_alert("avoirly-backup.service", environment=env, smtp_factory=FakeSMTP)
    assert result["duplicate_suppressed"]
    assert len(FakeSMTP.messages) == 1


def test_test_alert_does_not_hide_real_failure(env):
    notifier.send_alert("avoirly-backup.service", test=True, environment=env, smtp_factory=FakeSMTP)
    notifier.send_alert("avoirly-backup.service", environment=env, smtp_factory=FakeSMTP)
    assert len(FakeSMTP.messages) == 2


def test_failed_delivery_does_not_set_success_marker(env):
    FakeSMTP.fail = True
    with pytest.raises(RuntimeError):
        notifier.send_alert("avoirly-backup.service", environment=env, smtp_factory=FakeSMTP)
    assert not list(Path(env["AVOIRLY_ALERT_STATE_DIR"]).iterdir())


def test_header_injection_and_unknown_services_are_rejected(env):
    env["AVOIRLY_ALERT_EMAIL"] += "\r\nBcc: attacker@example.test"
    with pytest.raises(ValueError):
        notifier.send_alert("avoirly-backup.service", environment=env, smtp_factory=FakeSMTP)
    with pytest.raises(ValueError):
        notifier.send_alert("user-selected-command.service", environment=env, smtp_factory=FakeSMTP)
