"""In-memory PayPal simulator.

Used by the test-suite and by the optional PROOFPAY_FAKE_PAYPAL=1 development mode so the UI can be
exercised without sandbox credentials. It is NOT PayPal. The UI shows a loud banner whenever it is active,
and the hackathon demo must be recorded against the real sandbox.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .paypal import PayPalError


class FakePayPal:
    simulated = True

    def __init__(self):
        self._ids = itertools.count(1)
        self.orders: dict = {}
        self.auths: dict = {}
        self.captures: dict = {}
        self.calls: list = []
        # failure injection for tests: {"authorize": PayPalError(...), "capture": ..., "void": ...}
        self.fail: dict = {}
        self.fail_once: dict = {}
        self.capture_status = "COMPLETED"
        self.tamper_capture_amount: str | None = None

    def _maybe_fail(self, op: str):
        if op in self.fail_once:
            raise self.fail_once.pop(op)
        if op in self.fail:
            raise self.fail[op]

    def create_authorize_order(self, *, amount, currency, reference_id, description, request_id):
        self.calls.append(("create", amount, request_id))
        self._maybe_fail("create")
        oid = f"SIMORDER{next(self._ids):04d}"
        self.orders[oid] = {"amount": amount, "currency": currency, "reference_id": reference_id, "state": "CREATED"}
        return {"id": oid, "status": "CREATED", "intent": "AUTHORIZE"}

    def authorize_order(self, order_id, request_id):
        self.calls.append(("authorize", order_id, request_id))
        self._maybe_fail("authorize")
        order = self.orders.get(order_id)
        if not order:
            raise PayPalError("Order not found", status=404, issue="INVALID_RESOURCE_ID")
        aid = f"SIMAUTH{next(self._ids):04d}"
        created = datetime.now(timezone.utc).replace(microsecond=0)
        expires = created + timedelta(days=29)
        self.auths[aid] = {
            "amount": order["amount"], "currency": order["currency"], "status": "CREATED",
            "captured": Decimal("0.00"), "closed": False,
        }
        order["state"] = "COMPLETED"
        return {
            "id": order_id, "status": "COMPLETED", "intent": "AUTHORIZE",
            "purchase_units": [{
                "reference_id": order["reference_id"],
                "payments": {"authorizations": [{
                    "id": aid, "status": "CREATED",
                    "amount": {"currency_code": order["currency"], "value": order["amount"]},
                    "create_time": created.isoformat().replace("+00:00", "Z"),
                    "expiration_time": expires.isoformat().replace("+00:00", "Z"),
                }]},
            }],
        }

    def capture_authorization(self, authorization_id, *, amount, currency, final_capture, request_id, note=""):
        self.calls.append(("capture", authorization_id, amount, final_capture, request_id))
        self._maybe_fail("capture")
        auth = self.auths.get(authorization_id)
        if not auth:
            raise PayPalError("Authorization not found", status=404, issue="INVALID_RESOURCE_ID")
        if auth["closed"]:
            raise PayPalError("Already captured or voided", status=422, issue="AUTHORIZATION_ALREADY_CAPTURED")
        value = Decimal(amount)
        if value + auth["captured"] > Decimal(auth["amount"]):
            raise PayPalError("Capture exceeds authorization", status=422, issue="CAPTURE_AMOUNT_EXCEEDS")
        cid = f"SIMCAP{next(self._ids):04d}"
        auth["captured"] += value
        if final_capture:
            auth["closed"] = True
            auth["status"] = "CAPTURED"
        self.captures[cid] = {"amount": amount}
        shown = self.tamper_capture_amount or amount
        return {"id": cid, "status": self.capture_status, "final_capture": final_capture,
                "amount": {"currency_code": currency, "value": shown}}

    def void_authorization(self, authorization_id, request_id):
        self.calls.append(("void", authorization_id, request_id))
        self._maybe_fail("void")
        auth = self.auths.get(authorization_id)
        if not auth:
            raise PayPalError("Authorization not found", status=404, issue="INVALID_RESOURCE_ID")
        if auth["closed"]:
            raise PayPalError("Authorization already captured or voided", status=422,
                              issue="AUTHORIZATION_ALREADY_CAPTURED")
        auth["closed"] = True
        auth["status"] = "VOIDED"
        return {}

    def get_authorization(self, authorization_id):
        auth = self.auths.get(authorization_id)
        if not auth:
            raise PayPalError("Authorization not found", status=404)
        return {"id": authorization_id, "status": auth["status"]}
