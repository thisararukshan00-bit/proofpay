"""Small shared helpers: money, hashing, time, ids."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


def parse_money(value) -> Decimal:
    """Parse a user/PayPal amount into a 2-decimal Decimal. Raises ValueError on bad input."""
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("Amount must be a number.")
    if not d.is_finite():
        raise ValueError("Amount must be a number.")
    if d != d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
        raise ValueError("Amount can have at most 2 decimal places.")
    return d.quantize(Decimal("0.01"))


def fmt_money(d: Decimal) -> str:
    return f"{d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def floor_money(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_iso(value: str):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
