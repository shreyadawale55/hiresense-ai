from __future__ import annotations

from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip():
    hashed = hash_password("super-secret-password")

    assert verify_password("super-secret-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_round_trip():
    token = create_access_token(
        "recruiter@hiresense.ai",
        role="recruiter",
        user_id="00000000-0000-0000-0000-000000000001",
        additional_claims={"team": "talent"},
    )

    payload = decode_token(token)

    assert payload["sub"] == "recruiter@hiresense.ai"
    assert payload["role"] == "recruiter"
    assert payload["uid"] == "00000000-0000-0000-0000-000000000001"
    assert payload["team"] == "talent"
