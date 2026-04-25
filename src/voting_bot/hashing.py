from __future__ import annotations

import hmac
from hashlib import sha256


def hash_voter_id(user_id: int, secret: str) -> str:
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=str(user_id).encode("utf-8"),
        digestmod=sha256,
    ).hexdigest()
