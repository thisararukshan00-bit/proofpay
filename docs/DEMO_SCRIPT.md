# ProofPay: 3-minute demo script

**Before recording**
- Backend and frontend running. In `.env`: **PayPal sandbox credentials**, `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash-lite`,
  `GITHUB_TOKEN` (classic, no scopes), and `PROOFPAY_FAKE_PAYPAL` empty.
- Start the backend **without** `--reload` and check its first lines say
  `Verifier: gemini (gemini-3.5-flash-lite) | PayPal: sandbox`. The page header must say
  **PayPal sandbox · test money** and **AI verifier · gemini**.
- **Turn off Brave Shields (or any tracker blocker) for `localhost`**, or the PayPal popup can't report back and you
  get "PayPal checkout was closed". Let the popup close by itself; never close it by hand.
- **Reset demo data.** Two browser tabs: ProofPay and https://www.sandbox.paypal.com (logged in as the sandbox
  Business account, balance visible).
- Have the sandbox Personal (buyer) email and password ready, and the public repo you'll submit
  (`https://github.com/thisararukshan00-bit/GiftGenie` passes 4 of 5, so the partial-release path shows).
  Rehearse once. Don't show real credentials on screen.
- No third-party logos or copyrighted music in the video. Upload to YouTube as public, under 3 minutes.

**0:00 – 0:20 · The problem**
> "Freelancers finish the work and don't get paid. Clients pay upfront and get something else. ProofPay releases money
> on proof, not trust: PayPal holds the money, an AI checks the work against agreed criteria, and the client decides
> what to release."

Show the landing page and the sample receipt in the hero.

**0:20 – 0:50 · Agree the checks (AI #1)**
1. Client role → **New milestone**. Paste: "Build a small gift-finder web app and publish the code on GitHub with documentation."
2. **Suggest criteria**. Point at the three kinds: *checked by code*, *reviewed with evidence*, *your call*. Edit one line.
3. Create. "Both sides see these. They're locked and hashed once money is reserved."

**0:50 – 1:20 · Reserve with PayPal**
1. **Reserve the money** → PayPal button → log in with the sandbox buyer → approve.
2. Show the money bar: **On hold at PayPal**, and the authorization ID banner.
> "This is PayPal authorize, not a payment. The money is reserved, and nobody has been paid yet."

**1:20 – 2:05 · Submit and verify (AI #2) — the heart of the demo**
1. Switch to **Freelancer** → paste the repo URL → **Submit for verification**.
2. The **Proof Receipt** appears. Read one verified line aloud: criterion, verdict, and the quote with its file path.
3. **Point at the quote marked "(quote not found in the files)".**
> "Code checks the facts. The AI reviews the rest and has to quote the file. Here it gave two quotes: one is really in
> the README, the other it stitched together from two places — so ProofPay marks it unverified instead of hiding it.
> A 'pass' with no real quote is downgraded, and instructions hidden in a submission are treated as evidence, not orders."

**2:05 – 2:40 · The client decides**
1. Switch to **Client**. Show **Your decision**. Note the receipt only *suggests*.
2. **Pay part** → suggested amount → write a reason → confirm.
3. Status: **Partly paid**; the bar splits into paid and released back.
4. Switch to the sandbox PayPal tab, refresh: the captured amount arrived in the Business account.

**2:40 – 3:00 · Close**
> "Authorize, verify, capture. Partial release, revision, and void are all PayPal operations, and the AI never touches
> them. Zero-cost stack: FastAPI, React, PayPal sandbox, and any model you like."

Show the activity log with the PayPal IDs.

**Backup:** run `python -m pytest -q` in `backend/` (60 tests) and show the injection and evidence tests; or show the
**sample** paid milestone's receipt.
