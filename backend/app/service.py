"""ProofPay business logic: milestone lifecycle, PayPal authorize/capture/void, verification.

State machine
  draft --fund(authorize)--> funded --submit+verify--> verified --full capture--> paid
  verified --partial capture--> partially_paid
  verified --request revision--> revision_requested --submit+verify--> verified
  funded / verified / revision_requested --void--> voided
Side states: payment_pending (PayPal capture pending), authorization_expired, needs_attention.

Only a verified server-side PayPal response moves money states. The AI verifier only recommends.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from . import criteria as crit
from . import deliverable as dlv
from .ai import AIError
from .paypal import PayPalError
from .util import fmt_money, new_id, now_iso, parse_iso, parse_money
from .verifier import verify

OPEN_STATES = {"funded", "verified", "revision_requested"}
HONOR_DAYS = 3  # PayPal's documented honor period; the hold itself is valid for up to 29 days.


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


class ProofPayService:
    def __init__(self, store, paypal, settings, provider_factory=lambda: None, github_fetch=None):
        self.store = store
        self.paypal = paypal
        self.settings = settings
        self.provider_factory = provider_factory
        self.github_fetch = github_fetch or (lambda url: dlv.fetch_github(url, token=settings.github_token))
        self._lock = threading.RLock()

    # ----- helpers -----
    def _get(self, mid: str) -> dict:
        doc = self.store.get(mid)
        if not doc:
            raise ServiceError("Milestone not found.", 404)
        return doc

    @staticmethod
    def _event(doc: dict, etype: str, actor: str, **detail) -> None:
        doc.setdefault("events", []).append({"ts": now_iso(), "type": etype, "actor": actor, "detail": detail})

    @staticmethod
    def _require_role(actor: str, role: str, what: str) -> None:
        if actor != role:
            raise ServiceError(f"Only the {role} can {what}.", 403)

    def _begin(self, mid: str, allowed: set, what: str, actor: str, role: str) -> dict:
        """Lock a milestone for a slow operation. Duplicate clicks get a clear 409 instead of a double action."""
        self._require_role(actor, role, what)
        with self._lock:
            doc = self._get(mid)
            if doc.get("sample"):
                raise ServiceError("This is sample data and was not funded through PayPal.", 409)
            if doc.get("busy"):
                raise ServiceError("Another action on this milestone is still in progress. Wait a moment.", 409, "busy")
            if doc["status"] not in allowed:
                raise ServiceError(f"This milestone is '{doc['status']}', so you cannot {what} right now.", 409, "state")
            doc["busy"] = True
            self.store.save(doc)
            return doc

    def _end(self, mid: str, mutate=None) -> dict:
        with self._lock:
            doc = self._get(mid)
            if mutate:
                mutate(doc)
            doc["busy"] = False
            doc["updated_at"] = now_iso()
            self.store.save(doc)
            return doc

    # ----- read -----
    def list(self) -> list:
        items = self.store.list_milestones()
        items.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return [self.public(m) for m in items]

    def get(self, mid: str) -> dict:
        return self.public(self._get(mid))

    @staticmethod
    def public(doc: dict) -> dict:
        d = dict(doc)
        d.pop("_pending_order", None)
        d["money"] = ProofPayService.money_summary(doc)
        return d

    @staticmethod
    def money_summary(doc: dict) -> dict:
        pp = doc.get("paypal") or {}
        captured = sum((Decimal(c["amount"]) for c in pp.get("captures", []) if c.get("status") == "COMPLETED"),
                       Decimal("0.00"))
        reserved = Decimal("0.00")
        if doc["status"] in OPEN_STATES | {"payment_pending"} and pp.get("authorization_id"):
            reserved = Decimal(pp.get("authorized_amount", "0.00"))
        voided = Decimal(pp.get("authorized_amount", "0.00")) if doc["status"] == "voided" else Decimal("0.00")
        released = Decimal("0.00")
        if doc["status"] == "partially_paid":
            released = Decimal(pp.get("authorized_amount", "0.00")) - captured
        return {"reserved": fmt_money(reserved), "captured": fmt_money(captured),
                "voided": fmt_money(voided), "released_back": fmt_money(released)}

    # ----- create / edit -----
    def create(self, *, title: str, description: str, amount, deadline: str, criteria_raw: list,
               client: str, freelancer: str, actor: str) -> dict:
        self._require_role(actor, "client", "create a milestone")
        title, description = (title or "").strip(), (description or "").strip()
        if not (3 <= len(title) <= 100):
            raise ServiceError("Title must be 3 to 100 characters.")
        if len(description) > 4000:
            raise ServiceError("Description is too long.")
        try:
            amt = parse_money(amount)
        except ValueError as exc:
            raise ServiceError(str(exc))
        if not (Decimal("1.00") <= amt <= Decimal("1000.00")):
            raise ServiceError("Sandbox milestones must be between 1.00 and 1000.00.")
        try:
            criteria = crit.normalise(criteria_raw)
        except crit.CriteriaError as exc:
            raise ServiceError(str(exc))
        doc = {
            "id": new_id("ms"), "title": title, "description": description, "amount": fmt_money(amt),
            "currency": self.settings.currency, "deadline": (deadline or "")[:10],
            "client": client or "Client", "freelancer": freelancer or "Freelancer",
            "criteria": criteria, "criteria_hash": "", "criteria_frozen": False,
            "status": "draft", "busy": False, "paypal": {}, "submissions": [], "receipts": [], "events": [],
            "created_at": now_iso(), "updated_at": now_iso(), "sample": False,
        }
        self._event(doc, "created", "client", amount=doc["amount"], currency=doc["currency"])
        self.store.save(doc)
        return self.public(doc)

    def update_criteria(self, mid: str, criteria_raw: list, actor: str) -> dict:
        self._require_role(actor, "client", "edit criteria")
        with self._lock:
            doc = self._get(mid)
            if doc["status"] != "draft" or doc.get("busy"):
                raise ServiceError("Criteria are frozen once the milestone is funded.", 409, "frozen")
            try:
                doc["criteria"] = crit.normalise(criteria_raw)
            except crit.CriteriaError as exc:
                raise ServiceError(str(exc))
            doc.pop("_pending_order", None)  # an approval of an older order must not fund new criteria
            self._event(doc, "criteria_edited", "client", count=len(doc["criteria"]))
            doc["updated_at"] = now_iso()
            self.store.save(doc)
            return self.public(doc)

    # ----- funding: PayPal authorize -----
    def fund_create_order(self, mid: str, actor: str) -> dict:
        doc = self._begin(mid, {"draft"}, "fund this milestone", actor, "client")
        request_id = f"proofpay-order-{mid}-{new_id('n')}"
        try:
            order = self.paypal.create_authorize_order(
                amount=doc["amount"], currency=doc["currency"], reference_id=mid,
                description=f"ProofPay milestone: {doc['title']}", request_id=request_id)
        except PayPalError as exc:
            self._end(mid)
            raise self._map_paypal(exc, "start the PayPal checkout")
        order_id = order.get("id")
        if not order_id:
            self._end(mid)
            raise ServiceError("PayPal did not return an order ID.", 502)

        def mutate(d):
            d["_pending_order"] = order_id
            self._event(d, "paypal_order_created", "system", order_id=order_id, intent="AUTHORIZE")
        self._end(mid, mutate)
        return {"order_id": order_id, "simulated": bool(getattr(self.paypal, "simulated", False))}

    def fund_authorize(self, mid: str, order_id: str, actor: str) -> dict:
        doc = self._begin(mid, {"draft"}, "fund this milestone", actor, "client")
        if not order_id or order_id != doc.get("_pending_order"):
            self._end(mid)
            raise ServiceError("That PayPal order does not belong to this milestone's current checkout.", 409)
        try:
            resp = self.paypal.authorize_order(order_id, request_id=f"proofpay-auth-{mid}-{order_id}")
        except PayPalError as exc:
            def note(d):
                self._event(d, "paypal_authorize_failed", "system", issue=exc.issue or exc.kind, debug_id=exc.debug_id)
            self._end(mid, note)
            if exc.issue == "INSTRUMENT_DECLINED":
                raise ServiceError("PayPal declined that funding source. Choose another one and try again.", 402,
                                   "declined")
            raise self._map_paypal(exc, "authorize the payment")

        try:
            unit = resp["purchase_units"][0]
            auth = unit["payments"]["authorizations"][0]
            ok = (resp.get("id") == order_id and auth.get("status") == "CREATED"
                  and Decimal(auth["amount"]["value"]) == Decimal(doc["amount"])
                  and auth["amount"]["currency_code"] == doc["currency"])
        except (KeyError, IndexError, TypeError, ArithmeticError):
            ok = False
        if not ok:
            def note(d):
                self._event(d, "paypal_authorize_unverified", "system", order_id=order_id)
            self._end(mid, note)
            raise ServiceError("PayPal's authorization could not be verified (status, amount or currency "
                               "did not match). Nothing was recorded as funded.", 502)

        def mutate(d):
            d.pop("_pending_order", None)
            d["status"] = "funded"
            d["criteria_hash"] = crit.criteria_hash(d["criteria"])
            d["criteria_frozen"] = True
            d["paypal"] = {
                "order_id": order_id, "authorization_id": auth["id"], "authorization_status": auth["status"],
                "authorized_amount": d["amount"], "currency": d["currency"],
                "authorized_at": auth.get("create_time") or now_iso(),
                "expires_at": auth.get("expiration_time", ""),
                "honor_until": (parse_iso(auth.get("create_time") or now_iso()) + timedelta(days=HONOR_DAYS)).isoformat(),
                "captures": [], "capture_attempt": 0, "simulated": bool(getattr(self.paypal, "simulated", False)),
            }
            self._event(d, "funded", "client", authorization_id=auth["id"], amount=d["amount"],
                        criteria_hash=d["criteria_hash"])
        return self.public(self._end(mid, mutate))

    # ----- submit + verify -----
    def submit(self, mid: str, *, kind: str, url: str = "", text: str = "", filename: str = "", actor: str) -> dict:
        doc = self._begin(mid, {"funded", "revision_requested"}, "submit work", actor, "freelancer")
        if len(doc["submissions"]) >= 10:
            self._end(mid)
            raise ServiceError("This milestone has reached the 10 submission limit.", 409)
        try:
            if kind == "github":
                d = self.github_fetch(url)
            elif kind == "text":
                d = dlv.from_text(text, filename or "document")
            else:
                raise dlv.DeliverableError("Choose a GitHub repository or a document.")
        except dlv.DeliverableError as exc:
            self._end(mid, lambda x: self._event(x, "submission_rejected", "freelancer", reason=str(exc)[:200]))
            raise ServiceError(str(exc), 400)
        except Exception:  # noqa: BLE001 - never leave the milestone locked
            self._end(mid)
            raise
        try:
            sub_id = new_id("sub")
            receipt = verify(doc, d, self.provider_factory(), sub_id)
        except Exception:  # noqa: BLE001
            self._end(mid)
            raise

        def mutate(x):
            x["submissions"].append({"id": sub_id, "kind": d.kind, "label": d.label, "ref": d.ref, "sha": d.sha,
                                     "created_at": now_iso(), "receipt_id": receipt["id"]})
            x["receipts"].append(receipt)
            x["status"] = "verified"
            self._event(x, "submitted", "freelancer", ref=d.ref, kind=d.kind)
            self._event(x, "verified", "system", receipt_id=receipt["id"], mode=receipt["verifier"]["mode"],
                        recommendation=receipt["recommendation"], receipt_hash=receipt["receipt_hash"][:16])
        return self.public(self._end(mid, mutate))

    # ----- release: capture / revise / void -----
    def release(self, mid: str, *, action: str, confirm: bool, amount=None, reason: str = "", actor: str) -> dict:
        if action not in {"full", "partial", "revision", "void"}:
            raise ServiceError("Unknown action.")
        if not confirm:
            raise ServiceError("Please confirm this action.", 400, "confirm")
        reason = (reason or "").strip()[:500]
        if action == "void":
            return self._void(mid, reason, actor)
        if action == "revision":
            return self._revision(mid, reason, actor)
        return self._capture(mid, action, amount, reason, actor)

    def _revision(self, mid: str, reason: str, actor: str) -> dict:
        self._require_role(actor, "client", "request a revision")
        if len(reason) < 10:
            raise ServiceError("Tell the freelancer what to fix (at least 10 characters).")
        with self._lock:
            doc = self._get(mid)
            if doc.get("busy") or doc["status"] != "verified":
                raise ServiceError("A revision can only be requested after verification.", 409)
            doc["status"] = "revision_requested"
            self._event(doc, "revision_requested", "client", reason=reason)
            doc["updated_at"] = now_iso()
            self.store.save(doc)
            return self.public(doc)

    def _capture(self, mid: str, action: str, amount, reason: str, actor: str) -> dict:
        doc = self._begin(mid, {"verified"}, "release payment", actor, "client")
        pp = doc["paypal"]
        authorized = Decimal(pp["authorized_amount"])
        try:
            if action == "full":
                value = authorized
            else:
                try:
                    value = parse_money(amount)
                except ValueError as exc:
                    raise ServiceError(str(exc))
                if not (Decimal("0.01") <= value < authorized):
                    raise ServiceError(f"A partial amount must be between 0.01 and {fmt_money(authorized)} "
                                       "(less than the full amount).")
                if len(reason) < 10:
                    raise ServiceError("Explain why you are paying less (at least 10 characters).")
            if value > authorized:
                raise ServiceError("A capture can never exceed the authorized amount.")
            expires = parse_iso(pp.get("expires_at", ""))
            if expires and datetime.now(timezone.utc) > expires:
                self._end(mid, lambda d: (d.__setitem__("status", "authorization_expired"),
                                          self._event(d, "authorization_expired", "system")))
                raise ServiceError("This PayPal authorization has expired. Create a new milestone to pay.", 409)
        except ServiceError:
            with self._lock:
                d = self._get(mid)
                if d.get("busy") and d["status"] != "authorization_expired":
                    d["busy"] = False
                    self.store.save(d)
            raise

        attempt = pp.get("capture_attempt", 0)
        request_id = f"proofpay-cap-{mid}-{fmt_money(value)}-{attempt}"
        try:
            resp = self.paypal.capture_authorization(
                pp["authorization_id"], amount=fmt_money(value), currency=pp["currency"],
                final_capture=True, request_id=request_id,
                note=f"ProofPay milestone: {doc['title']}"[:255])
        except PayPalError as exc:
            def note(d):
                if exc.kind != "network":  # a network error keeps the same idempotency key for the retry
                    d["paypal"]["capture_attempt"] = attempt + 1
                self._event(d, "capture_failed", "system", issue=exc.issue or exc.kind, debug_id=exc.debug_id)
                if exc.issue == "AUTHORIZATION_EXPIRED":
                    d["status"] = "authorization_expired"
            self._end(mid, note)
            raise self._map_paypal(exc, "capture the payment")

        status = resp.get("status")
        try:
            amount_ok = (Decimal(resp["amount"]["value"]) == value and resp["amount"]["currency_code"] == pp["currency"])
        except (KeyError, TypeError, ArithmeticError):
            amount_ok = False
        if status not in {"COMPLETED", "PENDING"} or not amount_ok or not resp.get("id"):
            def flag(d):
                d["status"] = "needs_attention"
                self._event(d, "capture_unverified", "system", paypal_status=str(status))
            self._end(mid, flag)
            raise ServiceError("PayPal's capture response could not be verified. The milestone was flagged for "
                               "review and was not marked paid.", 502)

        def mutate(d):
            d["paypal"]["captures"].append({"id": resp["id"], "amount": fmt_money(value), "currency": pp["currency"],
                                            "status": status, "final_capture": True, "at": now_iso()})
            if status == "COMPLETED":
                d["status"] = "paid" if action == "full" else "partially_paid"
            else:
                d["status"] = "payment_pending"
            if action == "partial":
                d["partial_reason"] = reason
            self._event(d, "captured" if status == "COMPLETED" else "capture_pending", "client",
                        capture_id=resp["id"], amount=fmt_money(value), action=action,
                        **({"reason": reason} if reason else {}))
        return self.public(self._end(mid, mutate))

    def _void(self, mid: str, reason: str, actor: str) -> dict:
        doc = self._begin(mid, OPEN_STATES, "cancel and void", actor, "client")
        try:
            self.paypal.void_authorization(doc["paypal"]["authorization_id"],
                                           request_id=f"proofpay-void-{mid}")
        except PayPalError as exc:
            self._end(mid, lambda d: self._event(d, "void_failed", "system", issue=exc.issue or exc.kind,
                                                 debug_id=exc.debug_id))
            raise self._map_paypal(exc, "void the authorization")

        def mutate(d):
            d["status"] = "voided"
            self._event(d, "voided", "client", **({"reason": reason} if reason else {}))
        return self.public(self._end(mid, mutate))

    # ----- misc -----
    @staticmethod
    def _map_paypal(exc: PayPalError, doing: str) -> ServiceError:
        if exc.kind == "network":
            return ServiceError(f"Could not reach PayPal to {doing}. Nothing was changed - please try again.", 503,
                                "network")
        if exc.kind == "config":
            return ServiceError(str(exc), 503, "config")
        hint = f" (PayPal debug id: {exc.debug_id})" if exc.debug_id else ""
        if exc.issue == "AUTHORIZATION_ALREADY_CAPTURED":
            return ServiceError("PayPal says this authorization was already captured or voided." + hint, 409)
        if exc.issue == "AUTHORIZATION_EXPIRED":
            return ServiceError("The PayPal authorization has expired." + hint, 409)
        return ServiceError(f"PayPal could not {doing}: {exc}{hint}", 502)

    def suggest_criteria(self, description: str):
        try:
            return crit.suggest(description, self.provider_factory())
        except crit.CriteriaError as exc:
            raise ServiceError(str(exc))

    def reset(self) -> None:
        if not self.settings.allow_demo_reset:
            raise ServiceError("Demo reset is disabled.", 403)
        with self._lock:
            self.store.clear()
