"""
Tests for JWT security utilities — no database required.
"""
import pytest
from datetime import timedelta
from fastapi import HTTPException
from jose import jwt

from app.core.security import (
    create_access_token,
    decode_token,
    verify_password,
    get_password_hash,
)
from app.core.config import get_settings

settings = get_settings()


# ── Password hashing ──────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_produces_different_output(self):
        """Bcrypt hashes must not equal the plaintext."""
        hashed = get_password_hash("mysecurepassword")
        assert hashed != "mysecurepassword"

    def test_hash_verify_correct_password(self):
        password = "correct-horse-battery-staple"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True

    def test_hash_verify_wrong_password(self):
        hashed = get_password_hash("realpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_different_hashes(self):
        """Bcrypt uses random salts — same password must produce different hashes."""
        pw = "same-password"
        h1 = get_password_hash(pw)
        h2 = get_password_hash(pw)
        assert h1 != h2, "Bcrypt should produce different hashes for same password"

    def test_empty_password_hashes(self):
        """Empty password should be hashable without error."""
        hashed = get_password_hash("")
        assert isinstance(hashed, str)
        assert len(hashed) > 0


# ── JWT creation ──────────────────────────────────────────────────────────────

class TestAccessTokenCreation:
    def test_creates_string_token(self):
        token = create_access_token(data={"sub": "42"})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_token_has_three_parts(self):
        """JWT format: header.payload.signature"""
        token = create_access_token(data={"sub": "1"})
        parts = token.split(".")
        assert len(parts) == 3

    def test_token_contains_sub(self):
        token = create_access_token(data={"sub": "99"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "99"

    def test_token_contains_exp(self):
        token = create_access_token(data={"sub": "1"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert "exp" in payload

    def test_custom_expiry(self):
        """Token with longer expiry should have later exp timestamp."""
        import time
        token_short = create_access_token(data={"sub": "1"}, expires_delta=timedelta(minutes=1))
        token_long  = create_access_token(data={"sub": "1"}, expires_delta=timedelta(hours=24))
        p_short = jwt.decode(token_short, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        p_long  = jwt.decode(token_long,  settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert p_long["exp"] > p_short["exp"]

    def test_custom_payload_fields(self):
        token = create_access_token(data={"sub": "5", "email": "user@example.com", "admin": True})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["email"] == "user@example.com"
        assert payload["admin"] is True


# ── JWT decoding / verification ───────────────────────────────────────────────

class TestDecodeToken:
    def test_decode_valid_token(self):
        token = create_access_token(data={"sub": "7"})
        payload = decode_token(token)
        assert payload["sub"] == "7"

    def test_decode_invalid_token_raises_http_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    def test_decode_tampered_signature_raises(self):
        token = create_access_token(data={"sub": "1"})
        # Tamper with the signature part
        parts = token.split(".")
        tampered = f"{parts[0]}.{parts[1]}.invalidsignature"
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tampered)
        assert exc_info.value.status_code == 401

    def test_decode_expired_token_raises(self):
        token = create_access_token(
            data={"sub": "1"},
            expires_delta=timedelta(seconds=-10)   # Already expired
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_decode_wrong_secret_raises(self):
        """Token signed with a different secret must fail verification."""
        wrong_token = jwt.encode(
            {"sub": "1"},
            "completely-different-secret-key-that-is-long-enough",
            algorithm=settings.ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_token(wrong_token)
        assert exc_info.value.status_code == 401
