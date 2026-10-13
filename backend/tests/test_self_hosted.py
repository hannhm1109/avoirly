"""Self-hosting changes the configured origin, never the authentication boundary."""

import time
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from recovery.api.errors import DomainError
from recovery.auth import TokenVerifier
from recovery.config import Settings


def settings(tmp_path):
    return Settings(
        database_url="postgresql+psycopg://localhost/test?sslmode=require",
        storage_root=tmp_path,
        local_owner=None,
        mode="hosted",
        supabase_deployment="self_hosted",
        web_origin="https://avoirly.example",
        api_origin="https://api.avoirly.example",
        supabase_url="https://auth.avoirly.example",
        supabase_secret_key="sb_secret_test_only",
        metrics_token="test-metrics-" + "x" * 32,
        pilot_owner_ids=(uuid4(),),
    )


def test_custom_origin_requires_explicit_self_hosting(tmp_path):
    configured = settings(tmp_path)
    configured.validate()
    assert configured.hosted
    with pytest.raises(RuntimeError, match="managed Supabase"):
        replace(configured, supabase_deployment="managed").validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"supabase_deployment": "unknown"},
        {"supabase_url": "http://auth.avoirly.example"},
        {"supabase_url": "https://auth.avoirly.example/auth/v1"},
        {"supabase_url": "https://user:password@auth.avoirly.example"},
        {"supabase_url": "https://auth.avoirly.example?key=secret"},
        {"supabase_secret_key": "legacy-service-role-key"},
        {"local_owner": uuid4()},
        {"pilot_owner_ids": ()},
        {"database_url": "postgresql+psycopg://localhost/test"},
        {"web_origin": "http://avoirly.example"},
    ],
)
def test_self_hosting_retains_hosted_guards(tmp_path, changes):
    with pytest.raises(RuntimeError):
        replace(settings(tmp_path), **changes).validate()


def test_self_hosted_user_tokens_require_the_configured_issuer(tmp_path):
    configured = settings(tmp_path)
    private_key = ec.generate_private_key(ec.SECP256R1())

    class Keys:
        def get_signing_key_from_jwt(self, raw):
            return SimpleNamespace(key=private_key.public_key())

    verifier = TokenVerifier(configured, Keys())
    claims = {
        "sub": str(configured.pilot_owner_ids[0]),
        "iss": configured.supabase_url + "/auth/v1",
        "aud": "authenticated",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
        "role": "authenticated",
    }

    def signed(data):
        return jwt.encode(data, private_key, algorithm="ES256", headers={"kid": "test-key"})

    assert verifier.owner("Bearer " + signed(claims)) == configured.pilot_owner_ids[0]
    with pytest.raises(DomainError) as error:
        verifier.owner("Bearer " + signed({**claims, "iss": "https://other.supabase.co/auth/v1"}))
    assert error.value.status == 401
