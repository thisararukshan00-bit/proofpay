"""PayPal money flow, against the in-memory fake. Real sandbox payments need your own credentials."""
from decimal import Decimal

from app.paypal import PayPalError

from .conftest import CLIENT, FREELANCER


def get(env, mid):
    return env.client.get(f"/api/milestones/{mid}").json()


def test_fund_authorizes_and_freezes_criteria(env):
    mid = env.new_milestone("50.00")
    assert get(env, mid)["status"] == "draft"
    m = env.fund(mid)
    assert m["status"] == "funded"
    assert m["paypal"]["authorization_id"].startswith("SIMAUTH")
    assert m["criteria_frozen"] and len(m["criteria_hash"]) == 64
    assert m["money"]["reserved"] == "50.00" and m["money"]["captured"] == "0.00"
    # the order was created server-side with the STORED amount
    assert env.paypal.orders[m["paypal"]["order_id"]]["amount"] == "50.00"


def test_criteria_cannot_change_after_funding(env):
    mid = env.new_milestone()
    env.fund(mid)
    r = env.client.put(f"/api/milestones/{mid}/criteria", headers=CLIENT,
                       json=[{"text": "Something else entirely", "type": "manual"}])
    assert r.status_code == 409


def test_editing_criteria_invalidates_pending_order(env):
    mid = env.new_milestone()
    order = env.client.post(f"/api/milestones/{mid}/fund/create-order", headers=CLIENT).json()["order_id"]
    env.client.put(f"/api/milestones/{mid}/criteria", headers=CLIENT,
                   json=[{"text": "A new manual criterion", "type": "manual"}])
    r = env.client.post(f"/api/milestones/{mid}/fund/authorize", headers=CLIENT, json={"order_id": order})
    assert r.status_code == 409 and get(env, mid)["status"] == "draft"


def test_wrong_order_id_is_rejected(env):
    mid = env.new_milestone()
    env.client.post(f"/api/milestones/{mid}/fund/create-order", headers=CLIENT)
    r = env.client.post(f"/api/milestones/{mid}/fund/authorize", headers=CLIENT, json={"order_id": "SIMORDER9999"})
    assert r.status_code == 409 and get(env, mid)["status"] == "draft"


def test_full_capture_marks_paid_and_is_idempotent(env):
    mid = env.verified("50.00")
    r = env.release(mid, action="full")
    assert r.status_code == 200
    m = r.json()
    assert m["status"] == "paid" and m["money"]["captured"] == "50.00"
    assert m["paypal"]["captures"][0]["final_capture"] is True
    again = env.release(mid, action="full")  # duplicate click
    assert again.status_code == 409
    assert len([c for c in env.paypal.calls if c[0] == "capture"]) == 1


def test_release_requires_explicit_confirmation(env):
    mid = env.verified()
    r = env.release(mid, action="full", confirm=False)
    assert r.status_code == 400 and get(env, mid)["status"] == "verified"
    assert not [c for c in env.paypal.calls if c[0] == "capture"]


def test_partial_capture_needs_reason_and_less_than_full(env):
    mid = env.verified("50.00")
    assert env.release(mid, action="partial", amount="20.00").status_code == 400  # no reason
    assert env.release(mid, action="partial", amount="50.00", reason="paying the full amount here").status_code == 400
    assert env.release(mid, action="partial", amount="0.00", reason="because the work is missing").status_code == 400
    assert env.release(mid, action="partial", amount="60.00", reason="more than authorized!!").status_code == 400
    assert not [c for c in env.paypal.calls if c[0] == "capture"]
    r = env.release(mid, action="partial", amount="30.00", reason="Two of the three criteria were not met.")
    assert r.status_code == 200
    m = r.json()
    assert m["status"] == "partially_paid" and m["money"]["captured"] == "30.00"
    assert m["money"]["released_back"] == "20.00"
    assert env.paypal.calls[-1][3] is True  # final_capture releases the remainder


def test_over_capture_never_reaches_paypal_even_if_attempted(env):
    mid = env.verified("50.00")
    env.release(mid, action="partial", amount="50.01", reason="trying to take too much money")
    assert not [c for c in env.paypal.calls if c[0] == "capture"]


def test_void_releases_hold(env):
    mid = env.verified()
    r = env.release(mid, action="void", reason="Client cancelled")
    assert r.status_code == 200 and r.json()["status"] == "voided"
    assert r.json()["money"]["voided"] == "50.00"
    assert env.release(mid, action="full").status_code == 409  # cannot capture after void


def test_void_allowed_when_funded_but_not_submitted(env):
    mid = env.new_milestone()
    env.fund(mid)
    assert env.release(mid, action="void").json()["status"] == "voided"


def test_revision_loop_moves_no_money(env):
    mid = env.verified()
    r = env.release(mid, action="revision", reason="Please add a proper README run section.")
    assert r.json()["status"] == "revision_requested"
    assert not [c for c in env.paypal.calls if c[0] == "capture"]
    assert env.submit(mid).status_code == 200
    assert get(env, mid)["status"] == "verified" and len(get(env, mid)["receipts"]) == 2


def test_only_the_client_can_move_money_and_only_freelancer_submits(env):
    mid = env.verified()
    r = env.client.post(f"/api/milestones/{mid}/release", headers=FREELANCER, json={"action": "full", "confirm": True})
    assert r.status_code == 403
    mid2 = env.new_milestone()
    env.fund(mid2)
    r = env.client.post(f"/api/milestones/{mid2}/submit", headers=CLIENT, json={"kind": "github", "url": "x"})
    assert r.status_code == 403
    assert env.client.post(f"/api/milestones/{mid}/release", json={"action": "full", "confirm": True}).status_code == 401


def test_declined_funding_source_lets_buyer_retry(env):
    mid = env.new_milestone()
    order = env.client.post(f"/api/milestones/{mid}/fund/create-order", headers=CLIENT).json()["order_id"]
    env.paypal.fail_once["authorize"] = PayPalError("declined", status=422, issue="INSTRUMENT_DECLINED")
    r = env.client.post(f"/api/milestones/{mid}/fund/authorize", headers=CLIENT, json={"order_id": order})
    assert r.status_code == 402 and get(env, mid)["status"] == "draft" and not get(env, mid)["busy"]
    env.fund(mid)  # a fresh checkout works
    assert get(env, mid)["status"] == "funded"


def test_network_error_on_capture_changes_nothing_and_retry_reuses_idempotency_key(env):
    mid = env.verified()
    env.paypal.fail_once["capture"] = PayPalError("net", kind="network")
    r = env.release(mid, action="full")
    assert r.status_code == 503 and get(env, mid)["status"] == "verified" and not get(env, mid)["busy"]
    assert env.release(mid, action="full").status_code == 200
    keys = [c[4] for c in env.paypal.calls if c[0] == "capture"]
    assert len(keys) == 2 and keys[0] == keys[1]  # same PayPal-Request-Id => PayPal cannot charge twice


def test_api_error_on_capture_rotates_idempotency_key(env):
    mid = env.verified()
    env.paypal.fail_once["capture"] = PayPalError("nope", status=422, issue="TRANSACTION_REFUSED")
    assert env.release(mid, action="full").status_code == 502
    assert env.release(mid, action="full").status_code == 200
    keys = [c[4] for c in env.paypal.calls if c[0] == "capture"]
    assert keys[0] != keys[1]


def test_tampered_capture_amount_is_not_marked_paid(env):
    mid = env.verified("50.00")
    env.paypal.tamper_capture_amount = "1.00"
    r = env.release(mid, action="full")
    assert r.status_code == 502
    m = get(env, mid)
    assert m["status"] == "needs_attention" and m["money"]["captured"] == "0.00"


def test_pending_capture_is_not_paid(env):
    mid = env.verified()
    env.paypal.capture_status = "PENDING"
    m = env.release(mid, action="full").json()
    assert m["status"] == "payment_pending" and m["money"]["captured"] == "0.00"


def test_expired_authorization(env):
    mid = env.verified()
    doc = env.store.get(mid)
    doc["paypal"]["expires_at"] = "2020-01-01T00:00:00Z"
    env.store.save(doc)
    r = env.release(mid, action="full")
    assert r.status_code == 409 and get(env, mid)["status"] == "authorization_expired"


def test_busy_milestone_rejects_second_action(env):
    mid = env.verified()
    doc = env.store.get(mid)
    doc["busy"] = True
    env.store.save(doc)
    r = env.release(mid, action="full")
    assert r.status_code == 409 and r.json()["code"] == "busy"


def test_client_cannot_set_amount_through_release_or_create_limits(env):
    r = env.client.post("/api/milestones", headers=CLIENT, json={
        "title": "Too big", "amount": "99999.00", "criteria": [{"text": "A manual criterion", "type": "manual"}]})
    assert r.status_code == 400
    r = env.client.post("/api/milestones", headers=CLIENT, json={
        "title": "Odd amount", "amount": "10.005", "criteria": [{"text": "A manual criterion", "type": "manual"}]})
    assert r.status_code == 400


def test_events_form_an_audit_log(env):
    mid = env.verified()
    env.release(mid, action="full")
    types = [e["type"] for e in get(env, mid)["events"]]
    for expected in ["created", "paypal_order_created", "funded", "submitted", "verified", "captured"]:
        assert expected in types
    assert sum(Decimal(c["amount"]) for c in get(env, mid)["paypal"]["captures"]) == Decimal("50.00")


def test_sample_milestones_cannot_touch_paypal(env):
    sample = next(m for m in env.client.get("/api/milestones").json() if m["sample"])
    r = env.release(sample["id"], action="void")
    assert r.status_code == 409 and not env.paypal.calls


def test_config_exposes_client_id_but_never_the_secret(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.paypal import PayPalClient
    from app.storage import LocalJsonStore

    s = Settings(paypal_client_id="PUBLIC_ID", paypal_client_secret="TOP_SECRET_VALUE",
                 local_data_file=str(tmp_path / "d.json"))
    app = create_app(s, store=LocalJsonStore(s.local_data_file), paypal=PayPalClient("PUBLIC_ID", "TOP_SECRET_VALUE"),
                     provider_factory=lambda: None)
    body = TestClient(app).get("/api/config").text
    assert "PUBLIC_ID" in body and "TOP_SECRET_VALUE" not in body
    assert '"mode":"sandbox"' in body.replace(" ", "")


def test_paypal_client_only_talks_to_sandbox():
    import app.paypal as pp
    assert pp.SANDBOX_BASE == "https://api-m.sandbox.paypal.com"
    assert "api-m.paypal.com" not in open(pp.__file__).read().replace("api-m.sandbox.paypal.com", "")
