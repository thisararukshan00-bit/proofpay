"""FastAPI app: HTTP layer only. All rules live in service.py."""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai import get_provider
from .checks import CHECK_CATALOG
from .config import ROOT, Settings, load_settings
from .paypal import PayPalClient
from .paypal_fake import FakePayPal
from .seed import seed_if_empty
from .service import ProofPayService, ServiceError
from .storage import make_store

log = logging.getLogger("proofpay")
DEMO_USERS = {"client": "Nimal Stores", "freelancer": "Thisara"}


class CriteriaIn(BaseModel):
    text: str
    type: str
    check: dict | None = None


class MilestoneIn(BaseModel):
    title: str
    description: str = ""
    amount: str
    deadline: str = ""
    criteria: list[CriteriaIn]


class SuggestIn(BaseModel):
    description: str


class FundAuthorizeIn(BaseModel):
    order_id: str


class SubmitIn(BaseModel):
    kind: str
    url: str = ""
    text: str = ""
    filename: str = ""


class ReleaseIn(BaseModel):
    action: str
    confirm: bool = False
    amount: str | None = None
    reason: str = Field(default="", max_length=500)


def create_app(settings: Settings | None = None, *, store=None, paypal=None, provider_factory=None,
               github_fetch=None) -> FastAPI:
    settings = settings or load_settings()
    store = store or make_store(settings)
    if paypal is None:
        paypal = FakePayPal() if settings.fake_paypal else PayPalClient(settings.paypal_client_id,
                                                                        settings.paypal_client_secret)
    if provider_factory is None:
        provider = get_provider(settings)

        def provider_factory():
            return provider
    service = ProofPayService(store, paypal, settings, provider_factory, github_fetch)
    seed_if_empty(store, settings.currency)

    log.info("Verifier: %s%s | PayPal: %s", settings.ai_provider_name or "demo",
             f" ({settings.gemini_model})" if settings.ai_provider_name == "gemini" else "",
             "simulator" if settings.fake_paypal else "sandbox")

    app = FastAPI(title="ProofPay", version="1.0.0")
    app.state.service = service
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ServiceError)
    async def _service_error(_req: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status, content={"error": str(exc), "code": exc.code})

    def actor(x_demo_role: str = Header(default="")) -> str:
        if x_demo_role not in DEMO_USERS:
            raise HTTPException(status_code=401, detail="Choose a demo role (client or freelancer).")
        return x_demo_role

    @app.get("/api/config")
    def config():
        simulated = bool(getattr(paypal, "simulated", False))
        provider = provider_factory()
        return {
            "paypal": {"mode": "simulator" if simulated else "sandbox",
                       "configured": simulated or settings.paypal_configured,
                       "client_id": "" if simulated else settings.paypal_client_id,
                       "currency": settings.currency},
            "ai": {"mode": "ai" if provider else "demo", "provider": provider.name if provider else "",
                   "model": getattr(provider, "model", "") if provider else ""},
            "storage": store.name, "demo_users": DEMO_USERS, "check_catalog": CHECK_CATALOG,
            "github_token_set": bool(settings.github_token), "allow_demo_reset": settings.allow_demo_reset,
        }

    @app.get("/api/milestones")
    def list_milestones():
        return service.list()

    @app.get("/api/milestones/{mid}")
    def get_milestone(mid: str):
        return service.get(mid)

    @app.post("/api/milestones", status_code=201)
    def create_milestone(body: MilestoneIn, who: str = Depends(actor)):
        return service.create(title=body.title, description=body.description, amount=body.amount,
                              deadline=body.deadline, criteria_raw=[c.model_dump() for c in body.criteria],
                              client=DEMO_USERS["client"], freelancer=DEMO_USERS["freelancer"], actor=who)

    @app.put("/api/milestones/{mid}/criteria")
    def edit_criteria(mid: str, body: list[CriteriaIn], who: str = Depends(actor)):
        return service.update_criteria(mid, [c.model_dump() for c in body], who)

    @app.post("/api/criteria/suggest")
    def suggest(body: SuggestIn, who: str = Depends(actor)):
        criteria, mode, notice = service.suggest_criteria(body.description)
        return {"criteria": criteria, "mode": mode, "notice": notice}

    @app.post("/api/milestones/{mid}/fund/create-order")
    def fund_create(mid: str, who: str = Depends(actor)):
        return service.fund_create_order(mid, who)

    @app.post("/api/milestones/{mid}/fund/authorize")
    def fund_authorize(mid: str, body: FundAuthorizeIn, who: str = Depends(actor)):
        return service.fund_authorize(mid, body.order_id, who)

    @app.post("/api/milestones/{mid}/submit")
    def submit(mid: str, body: SubmitIn, who: str = Depends(actor)):
        return service.submit(mid, kind=body.kind, url=body.url, text=body.text, filename=body.filename, actor=who)

    @app.post("/api/milestones/{mid}/release")
    def release(mid: str, body: ReleaseIn, who: str = Depends(actor)):
        return service.release(mid, action=body.action, confirm=body.confirm, amount=body.amount,
                               reason=body.reason, actor=who)

    @app.post("/api/demo/reset")
    def reset(who: str = Depends(actor)):
        service.reset()
        seed_if_empty(store, settings.currency)
        return {"ok": True}

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            target = (dist / path).resolve()
            if path and dist.resolve() in target.parents and target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app
