"""PayPal REST client: Orders v2 (AUTHORIZE) + Payments v2 (capture / void). SANDBOX ONLY.

The base URL is a constant on purpose. There is no setting that can point this client at live PayPal.
"""
from __future__ import annotations

import base64
import threading
import time

import httpx

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"


class PayPalError(Exception):
    """A PayPal call failed. `kind` is 'network', 'api' or 'config'."""

    def __init__(self, message: str, *, kind: str = "api", status: int = 0, issue: str = "", debug_id: str = ""):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.issue = issue
        self.debug_id = debug_id


class PayPalClient:
    simulated = False

    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = http or httpx.Client(timeout=20.0)
        self._token = ""
        self._token_expiry = 0.0
        self._lock = threading.Lock()

    # ----- auth -----
    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expiry - 30:
                return self._token
            if not (self.client_id and self.client_secret):
                raise PayPalError("PayPal sandbox credentials are not configured.", kind="config")
            basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            try:
                resp = self._http.post(
                    f"{SANDBOX_BASE}/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {basic}"},
                )
            except httpx.HTTPError as exc:
                raise PayPalError(f"Could not reach PayPal: {exc.__class__.__name__}", kind="network") from exc
            if resp.status_code != 200:
                raise PayPalError(
                    "PayPal rejected the sandbox credentials. Use the Sandbox tab of Apps & Credentials.",
                    kind="config",
                    status=resp.status_code,
                )
            body = resp.json()
            self._token = body["access_token"]
            self._token_expiry = time.time() + int(body.get("expires_in", 300))
            return self._token

    def _request(self, method: str, path: str, *, json_body=None, request_id: str = ""):
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id[:108]
        try:
            resp = self._http.request(method, f"{SANDBOX_BASE}{path}", json=json_body, headers=headers)
        except httpx.HTTPError as exc:
            raise PayPalError(f"Could not reach PayPal: {exc.__class__.__name__}", kind="network") from exc
        if resp.status_code in (200, 201, 202):
            return resp.json() if resp.content else {}
        if resp.status_code == 204:
            return {}
        try:
            err = resp.json()
        except ValueError:
            err = {}
        issue = ""
        details = err.get("details") or []
        if details and isinstance(details[0], dict):
            issue = details[0].get("issue", "") or ""
        raise PayPalError(
            err.get("message") or f"PayPal returned HTTP {resp.status_code}.",
            kind="api",
            status=resp.status_code,
            issue=issue or err.get("name", ""),
            debug_id=err.get("debug_id", ""),
        )

    # ----- Orders v2 -----
    def create_authorize_order(self, *, amount: str, currency: str, reference_id: str, description: str, request_id: str):
        body = {
            "intent": "AUTHORIZE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "custom_id": reference_id,
                    "description": description[:127],
                    "amount": {"currency_code": currency, "value": amount},
                }
            ],
            "payment_source": {
                "paypal": {"experience_context": {"shipping_preference": "NO_SHIPPING", "user_action": "PAY_NOW"}}
            },
        }
        return self._request("POST", "/v2/checkout/orders", json_body=body, request_id=request_id)

    def authorize_order(self, order_id: str, request_id: str):
        return self._request("POST", f"/v2/checkout/orders/{order_id}/authorize", json_body={}, request_id=request_id)

    # ----- Payments v2 -----
    def capture_authorization(self, authorization_id: str, *, amount: str, currency: str, final_capture: bool,
                              request_id: str, note: str = ""):
        body = {"amount": {"currency_code": currency, "value": amount}, "final_capture": final_capture}
        if note:
            body["note_to_payer"] = note[:255]
        return self._request("POST", f"/v2/payments/authorizations/{authorization_id}/capture",
                             json_body=body, request_id=request_id)

    def void_authorization(self, authorization_id: str, request_id: str):
        return self._request("POST", f"/v2/payments/authorizations/{authorization_id}/void", request_id=request_id)

    def get_authorization(self, authorization_id: str):
        return self._request("GET", f"/v2/payments/authorizations/{authorization_id}")
