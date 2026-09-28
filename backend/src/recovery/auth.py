"""Verify managed user JWTs. Never derive ownership from unsigned client data."""

from uuid import UUID

import jwt
from jwt import PyJWKClient

from .api.errors import DomainError


class TokenVerifier:
    def __init__(self, settings, jwks=None):
        self.issuer = settings.supabase_url + "/auth/v1"
        self.allowed = set(settings.pilot_owner_ids)
        self.jwks = jwks or PyJWKClient(
            self.issuer + "/.well-known/jwks.json", timeout=5, lifespan=300, cache_keys=False
        )

    def owner(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise DomainError("UNAUTHENTICATED", "Sign in to access your cases.", 401)
        token = authorization[7:]
        if len(token) > 16384:
            raise DomainError("UNAUTHENTICATED", "Invalid session.", 401)
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ("ES256", "RS256") or not header.get("kid"):
                raise jwt.InvalidTokenError("Unsupported signing key")
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=10,
            )
            owner = UUID(claims["sub"])
            if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
                raise jwt.InvalidTokenError("User session required")
        except (
            jwt.InvalidTokenError,
            jwt.PyJWKClientError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            raise DomainError("UNAUTHENTICATED", "Invalid or expired session.", 401) from exc
        if owner not in self.allowed:
            raise DomainError(
                "PILOT_ACCESS_REQUIRED", "This account is not invited to the pilot.", 403
            )
        return owner
