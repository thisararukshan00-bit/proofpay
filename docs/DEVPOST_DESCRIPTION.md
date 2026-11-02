# Devpost description (draft)

## Inspiration
Freelancers in Sri Lanka and around the world finish work and then chase payment. Clients who pay upfront get work that doesn't match the brief. Both problems come from the same gap: nobody wrote down checkable criteria, and nobody holds objective evidence.

## What it does
ProofPay makes milestone payments that are released on proof, not on trust.
1. The client describes the job. An **AI Criteria Builder** turns it into testable acceptance criteria: checked by code, reviewed by AI with quoted evidence, or left to the client.
2. The client reserves the money with PayPal (**authorize now, capture later**). The criteria are locked and hashed.
3. The freelancer submits a public GitHub repo or a document. An **AI Proof Verifier** runs deterministic checks first, then reviews the rest. Every AI "pass" must quote evidence that really exists in the files.
4. ProofPay issues a **Proof Receipt**: criteria hash, commit SHA or document hash, verdict and evidence per criterion, and a recommendation.
5. The client decides: **pay in full, pay part (with a reason), ask for changes, or void the hold**. The AI recommends only. It can never move money.

## How we built it
FastAPI + React. PayPal Orders v2 with `intent=AUTHORIZE`, then Payments v2 capture (full or partial, `final_capture`) and void, with idempotency keys, a per-milestone lock, and server-side verification of every PayPal response. The AI layer supports Gemini or any OpenAI-compatible model behind one small interface, with a clearly labelled demo verifier when no key is set. 60 offline tests cover the money flow, prompt injection, evidence verification, and the GitHub fetcher.

## AI tools and models used
- **Criteria Builder:** an LLM (Gemini by default; configurable) turns a plain-language job description into criteria, restricted to a fixed catalog of deterministic checks.
- **Proof Verifier:** the same provider reviews submitted files against criteria and must return JSON with quoted evidence; output is validated, evidence is verified against the real files, and failures fall back to a labelled rule-based verifier.
- Built with the help of Claude (Anthropic) for code generation and review.

## Challenges
Making the AI useful without making it dangerous: untrusted submissions can contain hidden instructions, so content is fenced as data, evidence must be found verbatim, injection-looking text forces human review, and the verifier has no access to any payment function.

## What we learned
Authorize-and-capture is a better fit for milestone work than plain checkout: it gives the freelancer confidence the money exists, and it gives the client a real, PayPal-native way to release part or all of it.

## What's next
Reauthorization after PayPal's honor period, refunds, webhooks, real accounts, more deliverable types (design files, deployed URLs), and multi-milestone projects.

## Built with
Python, FastAPI, React, Vite, MongoDB, PayPal REST APIs (sandbox), Google Gemini, GitHub REST API, pytest
