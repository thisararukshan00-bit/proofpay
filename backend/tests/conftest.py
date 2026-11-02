import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deliverable import Deliverable
from app.main import create_app
from app.paypal_fake import FakePayPal
from app.storage import LocalJsonStore

CLIENT = {"X-Demo-Role": "client"}
FREELANCER = {"X-Demo-Role": "freelancer"}

README = """# Demo App

A tiny gift finder for small shops.

## How to run
Run `npm install` then `npm start`.
"""


def fake_repo(**overrides) -> Deliverable:
    d = Deliverable(
        kind="github", label="owner/repo", ref="https://github.com/owner/repo@abc1234567", sha="abc1234567" * 4,
        files={"README.md": README, "LICENSE": "MIT License\nCopyright (c) 2026", "test/a.test.js": "it('works')"},
        tree=["README.md", "LICENSE", "test/a.test.js", "src/index.js"], ci="success",
    )
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


class Env:
    def __init__(self, tmp_path):
        self.settings = Settings(local_data_file=str(tmp_path / "data.json"))
        self.paypal = FakePayPal()
        self.store = LocalJsonStore(self.settings.local_data_file)
        self.repo = fake_repo()
        self.provider = None
        app = create_app(self.settings, store=self.store, paypal=self.paypal,
                         provider_factory=lambda: self.provider, github_fetch=lambda url: self.repo)
        self.client = TestClient(app)
        self.service = app.state.service

    def new_milestone(self, amount="50.00", criteria=None) -> str:
        criteria = criteria or [
            {"text": "README has a section on how to run it.", "type": "automatic",
             "check": {"name": "readme_has_section", "param": "run|usage"}},
            {"text": "The repository has a LICENSE file.", "type": "automatic",
             "check": {"name": "license_exists", "param": None}},
            {"text": "The client likes the look and feel.", "type": "manual", "check": None},
        ]
        r = self.client.post("/api/milestones", headers=CLIENT, json={
            "title": "Build the app", "description": "x", "amount": amount, "criteria": criteria})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def fund(self, mid):
        o = self.client.post(f"/api/milestones/{mid}/fund/create-order", headers=CLIENT)
        assert o.status_code == 200, o.text
        r = self.client.post(f"/api/milestones/{mid}/fund/authorize", headers=CLIENT,
                             json={"order_id": o.json()["order_id"]})
        assert r.status_code == 200, r.text
        return r.json()

    def submit(self, mid):
        return self.client.post(f"/api/milestones/{mid}/submit", headers=FREELANCER,
                                json={"kind": "github", "url": "https://github.com/owner/repo"})

    def release(self, mid, **body):
        body.setdefault("confirm", True)
        return self.client.post(f"/api/milestones/{mid}/release", headers=CLIENT, json=body)

    def verified(self, amount="50.00"):
        mid = self.new_milestone(amount)
        self.fund(mid)
        assert self.submit(mid).status_code == 200
        return mid


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
