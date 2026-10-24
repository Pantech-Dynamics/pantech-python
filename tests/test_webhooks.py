from __future__ import annotations

import hashlib
import hmac

import pytest

import pantech

SECRET = "whsec_test_secret"
BODY = b'{"id":"evt_1","type":"instance.created"}'
NOW = 1_800_000_000


def sign(secret: str, t: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()


def test_valid_signature() -> None:
    header = f"t={NOW},v1={sign(SECRET, NOW, BODY)}"
    assert pantech.verify_webhook(SECRET, header, BODY, now=NOW) is None


def test_str_body_and_bytes_secret() -> None:
    header = f"t={NOW},v1={sign(SECRET, NOW, BODY)}"
    pantech.verify_webhook(SECRET.encode(), header, BODY.decode(), now=NOW + 10)


def test_any_of_several_v1_values_after_rotation() -> None:
    header = f"t={NOW},v1={sign('whsec_new', NOW, BODY)},v1={sign(SECRET, NOW, BODY)}"
    pantech.verify_webhook(SECRET, header, BODY, now=NOW)
    pantech.verify_webhook("whsec_new", header, BODY, now=NOW)


def test_spaces_around_parts_are_fine() -> None:
    header = f"t={NOW}, v1={sign(SECRET, NOW, BODY)}"
    pantech.verify_webhook(SECRET, header, BODY, now=NOW)


@pytest.mark.parametrize(
    ("header", "body", "now", "match"),
    [
        (f"t={NOW},v1={sign('whsec_other', NOW, BODY)}", BODY, NOW, "No signature matches"),
        (f"t={NOW},v1={sign(SECRET, NOW, BODY)}", BODY + b" ", NOW, "No signature matches"),
        (f"t={NOW},v1={sign(SECRET, NOW, BODY)}", BODY, NOW + 301, "tolerance"),
        (f"t={NOW},v1={sign(SECRET, NOW, BODY)}", BODY, NOW - 301, "tolerance"),
        (f"t={NOW + 1},v1={sign(SECRET, NOW, BODY)}", BODY, NOW, "No signature matches"),
        (f"v1={sign(SECRET, NOW, BODY)}", BODY, NOW, "timestamp"),
        (f"t=abc,v1={sign(SECRET, NOW, BODY)}", BODY, NOW, "timestamp"),
        (f"t={NOW}", BODY, NOW, "no v1"),
        (f"t={NOW},v0={sign(SECRET, NOW, BODY)}", BODY, NOW, "no v1"),
        ("", BODY, NOW, "Missing"),
        (f"t={NOW},v1=ünïcode", BODY, NOW, "No signature matches"),
    ],
)
def test_rejections(header: str, body: bytes, now: int, match: str) -> None:
    with pytest.raises(pantech.WebhookVerificationError, match=match):
        pantech.verify_webhook(SECRET, header, body, now=now)


def test_custom_tolerance_and_none() -> None:
    header = f"t={NOW},v1={sign(SECRET, NOW, BODY)}"
    with pytest.raises(pantech.WebhookVerificationError):
        pantech.verify_webhook(SECRET, header, BODY, tolerance=10, now=NOW + 11)
    pantech.verify_webhook(SECRET, header, BODY, tolerance=None, now=NOW + 10_000)


def test_empty_secret_is_refused() -> None:
    with pytest.raises(pantech.WebhookVerificationError):
        pantech.verify_webhook("", "t=1,v1=00", BODY)


def test_uses_constant_time_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    real = hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    header = f"t={NOW},v1={sign(SECRET, NOW, BODY)},v1=00"
    pantech.verify_webhook(SECRET, header, BODY, now=NOW)
    assert len(calls) == 2
