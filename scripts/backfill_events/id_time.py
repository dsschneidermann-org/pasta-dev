"""Cut from src/ids.py, where it sat beside `new_token`, whose `_ALPHABET` it reads."""


def id_time(identifier: str) -> float | None:
    """Epoch seconds encoded in an id or token made by `new_id` / `new_token`, or None when the
    token does not start with base-36 millis."""
    token = identifier.rsplit(":", 1)[-1]
    millis = token.split("-", 1)[0]
    if not millis or any(ch not in _ALPHABET for ch in millis):
        return None
    return int(millis, 36) / 1000
