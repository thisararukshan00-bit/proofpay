# ProofPay

**Milestone payments that are released on proof, not on trust.**

A client reserves the money with PayPal. The freelancer submits the work. ProofPay checks it against the agreed
acceptance criteria and issues a **Proof Receipt** with quoted evidence. Then the client decides: pay in full, pay part
(with a reason), ask for changes, or void the hold. **The AI only recommends. It can never move money.**

Built for the [PayPal AI Hackathon](https://paypalaihackathon.devpost.com/). Sandbox only: no real money moves.

> ProofPay is **not** an escrow service. It uses PayPal's documented *authorize now, capture later* flow.
> PayPal's honor period is 3 days and a hold lasts up to 29 days; after the honor period a capture can need a
> reauthorization (not implemented, see Known limitations).

## The problem

Freelancers finish work and don't get paid. Clients pay upfront and get work that doesn't match the brief. Disputes drag
on because nobody wrote down checkable criteria and nobody has objective evidence. ProofPay reserves the money before
work starts and bases release on criterion-by-criterion evidence that both sides can read.

## How it works

```
Client describes the job ──► AI Criteria Builder ──► editable criteria (checked by code / reviewed with evidence / client's call)
Client approves in PayPal ──► POST /v2/checkout/orders (intent=AUTHORIZE) ──► .../authorize   = money on hold, criteria frozen + hashed
Freelancer submits (GitHub URL or document)
   ├─ deterministic checks (plain code, final)
   ├─ AI review: every "pass" needs a quote that really exists in the files, or it is downgraded
   └─ Proof Receipt (criteria hash, commit SHA / document hash, verdicts, evidence, receipt hash)
Client decides ──► full capture | partial capture (+reason) | request revision | void
                   (POST /v2/payments/authorizations/{id}/capture | .../void, always final_capture=true, idempotent)
```

### Safety rules built in

| Rule | Where |
|---|---|
| The AI recommends only; capture/void are separate endpoints needing the client role and an explicit `confirm` | `service.py` |
| Amounts come from the stored milestone. The browser never sends a price; a capture can never exceed the authorization | `service.py`, tests |
| "Paid" only after PayPal's capture response is verified (status, amount, currency). Tampered or pending responses are not paid | `service.py`, tests |
| Duplicate clicks: a per-milestone lock plus `PayPal-Request-Id`. A network error retries with the same key, so PayPal cannot charge twice | `service.py`, tests |
| Submitted files are untrusted data: fenced in a nonce-delimited block, the model is told to ignore embedded instructions, injection-looking text is flagged and forces "review before paying" | `verifier.py` |
| An AI "pass" needs a quote found verbatim in the submitted files, or it becomes "unclear". Line wrapping and curly quotes are normalised; changed words, reordered fragments and text stitched from two places are not accepted, and each unverified quote is shown as such on the receipt | `verifier.py`, tests |
| AI output is validated with Pydantic; invalid output or provider failure falls back to the labelled demo verifier | `verifier.py` |
| `manual` criteria are never auto-passed. Deterministic check results can't be overridden by the AI | `verifier.py`, tests |
| Submitted code is never cloned or run. Only `api.github.com` is ever contacted; the URL is parsed, not fetched | `deliverable.py`, tests |
| PayPal base URL is a constant (`api-m.sandbox.paypal.com`). The secret never reaches the browser | `paypal.py`, tests |

## Stack

FastAPI (Python) · React + Vite · MongoDB or an automatic local JSON file · PayPal Orders v2 + Payments v2 (sandbox) ·
Google Gemini or any OpenAI-compatible model, or the labelled Demo verifier · pytest (60 tests, offline, fake PayPal).

## Run it locally

Prerequisites: Python 3.10+, Node.js 20+.

```bash
cp .env.example .env          # then edit .env
```

**Terminal 1: backend** (http://127.0.0.1:8000)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.asgi:app --reload --port 8000
```

**Terminal 2: frontend** (http://localhost:5173)
```bash
cd frontend
npm install
npm run dev
```

Single-process mode: run `npm run build` in `frontend/`, then start only the backend. It serves the built app at
http://127.0.0.1:8000.

Tests: `cd backend && pip install -r requirements-dev.txt && python -m pytest -q`

## For judges: try it in 5 minutes

1. Follow **Run it locally** and the **PayPal sandbox setup** below (or open the hosted demo link on the Devpost page, if one is listed).
2. Open the seeded draft milestone, click **Reserve the money**, and sign in to the PayPal popup with the sandbox
   **Personal (buyer)** account (credentials are given in the Devpost "testing instructions", never in the repo).
3. Switch to **Freelancer**, paste a public GitHub repo URL, and click **Submit for verification**.
4. Read the **Proof Receipt**, switch to **Client**, and choose **Pay part** (or **Pay in full**, **Ask for changes**, **Cancel**).
5. Sign in at https://www.sandbox.paypal.com with the sandbox **Business** account to see the captured amount.

Use **Reset demo data** on the Milestones page to repeat the run. Only sandbox test money is ever involved.

## PayPal sandbox setup (free, test money only)

1. Sign in at https://developer.paypal.com.
2. **Testing tools → Sandbox accounts.** Make sure you have one **Business** (seller) and one **Personal** (buyer) account.
   Open the Personal account → *View/Edit account* to see its email and password.
3. **Apps & Credentials**, toggle **Sandbox**, create an app (Merchant) linked to the Business account. Copy the Client ID and Secret.
4. Put them in `.env` as `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`, restart the backend.
5. In the app: *Reserve the money* shows PayPal buttons. Sign in with the **sandbox Personal** account.
6. After a release, sign in at https://www.sandbox.paypal.com with the sandbox Business account to see the captured money.

The header shows **PayPal sandbox · test money**. If it shows **PayPal simulator**, `PROOFPAY_FAKE_PAYPAL` is on.

## AI setup (optional)

Set `GEMINI_API_KEY` (free keys are available from Google AI Studio; check current terms) or an OpenAI-compatible
`AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL`. The header badge switches from **Demo verifier** to **AI verifier**.
Without a key, criteria come from simple rules and judgement criteria are matched by keywords. The receipt says so on its face.

## Demo data

On first start: one **draft** milestone ready for your live PayPal demo (with a public repo suggested), and one **sample**
paid milestone with a real generated receipt. Sample records carry no PayPal IDs and can't be captured or voided.
Use **Reset demo data** on the Milestones page to start over (PayPal holds already made stay at PayPal until they expire).

## Roles

The Client/Freelancer switch is a demo role header, **not authentication**. The server enforces which role may do what,
but a real deployment needs real accounts.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Can't reach the ProofPay server" | Start the backend on port 8000, or run the frontend with `VITE_API_PROXY=http://127.0.0.1:PORT npm run dev`. |
| "PayPal sandbox isn't set up" | Set both PayPal variables in `.env`, restart the backend. |
| "PayPal rejected the sandbox credentials" | Use the **Sandbox** tab's credentials, not Live. |
| "Couldn't load PayPal" | Offline, ad blocker, or wrong client ID. |
| "PayPal checkout was closed. Nothing was held" even though PayPal said "Thanks for using PayPal" | A browser privacy feature (for example Brave Shields) blocked the popup's message back to the page. Turn Shields off for `localhost`, retry, and let the popup close by itself. |
| Checkout popup errors on order creation | Check the backend log for PayPal's `debug_id`; see "Known limitations" (order request shape). |
| "GitHub rate limit reached", or "No README file was available to read" for a repo that has one | Set `GITHUB_TOKEN` (a classic token with no scopes) and restart the backend, or wait an hour. |
| Backend logs "MongoDB unavailable… Falling back" | Check `MONGODB_URI` and IP allowlist, or ignore it: the JSON file works. |

## Known limitations (honest list)

- **Tested end to end on the real PayPal sandbox (1 Nov 2026):** authorize (hold of $25.00), GitHub submission, Proof
  Receipt, and a **partial capture of $15.00 with `final_capture`**, after which the rest of the hold was released.
  The automated tests still use a fake PayPal so they run offline. Full capture and void are covered by those tests;
  re-run them on the sandbox before relying on them.
- **The Gemini verifier was tested the same way (2 Nov 2026):** a live review of a public repo returned verdicts with
  quoted evidence, one quote verified against the file and one — stitched together from two places — correctly flagged
  as not found. MongoDB was not exercised; the local JSON store was used.
- Gemini model names move: a shut-down model answers `404`, and a large "thinking" model can exceed the request
  timeout. Set `GEMINI_MODEL` to a current fast model (default `gemini-3.5-flash-lite`) and raise
  `AI_TIMEOUT_SECONDS` if needed. The receipt always states which verifier actually ran, and why a fallback happened.
- No reauthorization after the 3-day honor period, no refunds of captures, no webhooks. The UI shows the honor and expiry
  dates so judges and users aren't surprised.
- Authorization status is read from the authorize response, not re-polled.
- Verification runs inline in the request (a few seconds); large repos are sampled (14 files, 150 KB).
- Demo-verifier language understanding is keyword-based, and the UI says so.
- Single shared demo identity per role. No real auth, no multi-currency (USD only; PayPal doesn't support LKR).

## License

MIT. See [LICENSE](LICENSE).
