"""Demo data. Sample records are labelled `sample: true` and carry no PayPal ids, so they can never be
captured or voided. The live demo uses the draft milestone, which is funded through the real PayPal sandbox."""
from __future__ import annotations

from . import criteria as crit
from . import deliverable as dlv
from .util import fmt_money, new_id, now_iso
from .verifier import verify

SAMPLE_DOC = """# Sinhala New Year Campaign - Blog Post

Avurudu is the season when every Sri Lankan household slows down, cleans the home, lights the hearth and
shares kiribath with neighbours. In this post we look at three small shops that built their Avurudu sales
around that spirit of sharing.

## 1. Bundle the traditions
Customers do not buy single items at Avurudu. They buy a whole table: kokis, kavum, asmi and a bottle of
coconut oil. Shops that sold ready-made bundles saw baskets that were more than twice the usual size.

## 2. Be honest about stock
One shop posted a daily stock list on its page every morning at eight. People trusted the list, planned their
visit, and the owner stopped answering the same question forty times a day.

## 3. Thank people in Sinhala and English
A short thank-you note in both languages, placed inside every parcel, cost almost nothing and was mentioned
in many reviews.

## Conclusion
Small habits create the trust that festive shoppers remember. Start early, share stock honestly and say thank
you in the customer's own language. """ + ("The festive season rewards shops that treat every parcel as a gift. " * 12)


def _sample_paid(client: str, freelancer: str, currency: str) -> dict:
    criteria = crit.normalise([
        {"text": "The blog post is at least 200 words long.", "type": "automatic",
         "check": {"name": "min_words", "param": "200"}},
        {"text": "The post mentions Avurudu.", "type": "automatic", "check": {"name": "text_contains", "param": "Avurudu"}},
        {"text": "The post gives three practical tips for small shops.", "type": "ai_review", "check": None},
        {"text": "The client is happy with the tone.", "type": "manual", "check": None},
    ])
    doc = {
        "id": new_id("ms"), "title": "Sample: Avurudu blog post (already paid)",
        "description": "Sample data that shows what a finished milestone and its Proof Receipt look like.",
        "amount": "40.00", "currency": currency, "deadline": "2026-04-10", "client": client, "freelancer": freelancer,
        "criteria": criteria, "criteria_hash": crit.criteria_hash(criteria), "criteria_frozen": True,
        "status": "paid", "busy": False, "sample": True,
        "paypal": {"order_id": "SAMPLE-ONLY", "authorization_id": "SAMPLE-ONLY", "authorized_amount": "40.00",
                   "currency": currency, "captures": [{"id": "SAMPLE-ONLY", "amount": "40.00", "currency": currency,
                                                       "status": "COMPLETED", "final_capture": True, "at": now_iso()}],
                   "capture_attempt": 0, "simulated": True},
        "submissions": [], "receipts": [], "events": [], "created_at": "2026-04-01T09:00:00+00:00",
        "updated_at": now_iso(),
    }
    sub_id = new_id("sub")
    d = dlv.from_text(SAMPLE_DOC, "avurudu-post.md")
    receipt = verify(doc, d, None, sub_id)
    doc["submissions"].append({"id": sub_id, "kind": d.kind, "label": d.label, "ref": d.ref, "sha": d.sha,
                               "created_at": now_iso(), "receipt_id": receipt["id"]})
    doc["receipts"].append(receipt)
    for etype, actor, detail in [("created", "client", {"amount": "40.00"}),
                                 ("funded", "client", {"note": "sample data - no PayPal call"}),
                                 ("submitted", "freelancer", {"ref": d.ref}),
                                 ("verified", "system", {"recommendation": receipt["recommendation"]}),
                                 ("captured", "client", {"amount": "40.00", "note": "sample data - no PayPal call"})]:
        doc["events"].append({"ts": now_iso(), "type": etype, "actor": actor, "detail": detail})
    return doc


def _draft_repo_milestone(client: str, freelancer: str, currency: str) -> dict:
    criteria = crit.normalise([
        {"text": "The README has a section explaining how to run the project.", "type": "automatic",
         "check": {"name": "readme_has_section", "param": "run|usage|install|setup"}},
        {"text": "The repository includes an open-source LICENSE file.", "type": "automatic",
         "check": {"name": "license_exists", "param": None}},
        {"text": "The repository includes automated tests.", "type": "automatic",
         "check": {"name": "tests_exist", "param": None}},
        {"text": "The README explains what the project does for its users.", "type": "ai_review", "check": None},
        {"text": "The client is happy with the overall quality.", "type": "manual", "check": None},
    ])
    return {
        "id": new_id("ms"), "title": "Build a gift-finder web app (demo)",
        "description": "Live demo milestone: fund it with the PayPal sandbox, then submit a public GitHub repo, "
                       "for example https://github.com/thisararukshan00-bit/GiftGenie",
        "amount": "25.00", "currency": currency, "deadline": "",
        "client": client, "freelancer": freelancer, "criteria": criteria, "criteria_hash": "",
        "criteria_frozen": False, "status": "draft", "busy": False, "sample": False, "paypal": {},
        "submissions": [], "receipts": [],
        "events": [{"ts": now_iso(), "type": "created", "actor": "client", "detail": {"amount": "25.00"}}],
        "created_at": now_iso(), "updated_at": now_iso(),
    }


def seed_if_empty(store, currency: str = "USD", client: str = "Nimal Stores", freelancer: str = "Thisara") -> None:
    if store.list_milestones():
        return
    store.save(_draft_repo_milestone(client, freelancer, currency))
    store.save(_sample_paid(client, freelancer, currency))
