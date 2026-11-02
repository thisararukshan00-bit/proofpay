import React, { useCallback, useEffect, useState } from "react";
import { STATUS, api, fmtDate, money, setRole } from "./api.js";
import { Banner, CriteriaEditor, MoneyBar, PayPalFund, Receipt, StatusChip } from "./components.jsx";

function useHashRoute() {
  const read = () => window.location.hash.replace(/^#/, "") || "/";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
const go = (path) => { window.location.hash = path; };

function initialRole() {
  try { return window.localStorage.getItem("proofpay-role") === "freelancer" ? "freelancer" : "client"; } catch { return "client"; }
}

export default function App() {
  const route = useHashRoute();
  const [role, setRoleState] = useState(initialRole);
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  setRole(role);

  const chooseRole = (r) => {
    setRoleState(r);
    try { window.localStorage.setItem("proofpay-role", r); } catch { /* storage unavailable */ }
  };
  useEffect(() => { api.config().then(setConfig).catch((e) => setConfigError(e.message)); }, []);

  const m = route.match(/^\/m\/([\w-]+)$/);
  let page;
  if (configError) page = <main className="wrap"><Banner tone="bad">{configError}</Banner></main>;
  else if (!config) page = <main className="wrap"><p className="muted">Loading…</p></main>;
  else if (route === "/") page = <Landing config={config} />;
  else if (route === "/dashboard") page = <Dashboard role={role} config={config} />;
  else if (route === "/new") page = <NewMilestone role={role} config={config} />;
  else if (m) page = <MilestoneDetail key={m[1] + role} id={m[1]} role={role} config={config} />;
  else page = <main className="wrap"><h1>Page not found</h1><a href="#/dashboard">Back to milestones</a></main>;

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <Header role={role} onRole={chooseRole} config={config} />
      <div id="main">{page}</div>
      <footer className="site-foot wrap">
        ProofPay is a hackathon prototype. Payments use the PayPal sandbox with test money only. ProofPay is not an escrow service: it uses PayPal's authorize-and-capture.
      </footer>
    </>
  );
}

function Header({ role, onRole, config }) {
  return (
    <header className="topbar">
      <div className="wrap topbar-in">
        <a className="logo" href="#/" aria-label="ProofPay home"><span className="logo-mark" aria-hidden="true">✓</span>ProofPay</a>
        <nav aria-label="Main"><a href="#/dashboard">Milestones</a></nav>
        <div className="topbar-right">
          {config && (
            <>
              <span className={`badge ${config.paypal.mode === "simulator" ? "tone-bad" : "tone-info"}`}
                    title="PayPal mode">{config.paypal.mode === "simulator" ? "PayPal simulator" : "PayPal sandbox · test money"}</span>
              <span className="badge" title="Who checks the work">{config.ai.mode === "ai" ? `AI verifier · ${config.ai.provider}` : "Demo verifier"}</span>
            </>
          )}
          <div className="seg-toggle" role="group" aria-label="Demo role">
            <button className={role === "client" ? "on" : ""} aria-pressed={role === "client"} onClick={() => onRole("client")}>Client</button>
            <button className={role === "freelancer" ? "on" : ""} aria-pressed={role === "freelancer"} onClick={() => onRole("freelancer")}>Freelancer</button>
          </div>
        </div>
      </div>
    </header>
  );
}

function Landing({ config }) {
  return (
    <main>
      <section className="hero wrap">
        <div className="hero-copy">
          <h1>Pay when the proof is in.</h1>
          <p className="lead">
            The client reserves the money with PayPal. The freelancer hands in the work. ProofPay checks it against
            the agreed criteria, line by line, and issues a receipt with the evidence. Then the client decides what to release.
          </p>
          <div className="actions">
            <a className="btn" href="#/dashboard">Open the demo</a>
            <a className="btn ghost" href="#/new">Create a milestone</a>
          </div>
          {config.paypal.mode === "simulator" && <Banner tone="bad">Simulator mode is on: payments on this screen are not real PayPal.</Banner>}
        </div>
        <div className="hero-receipt" aria-hidden="true">
          <div className="mini-receipt">
            <p className="receipt-brand">PROOFPAY</p>
            <p className="receipt-title">Proof receipt</p>
            <div className="row-between"><span>README explains how to run it</span><b className="verdict tone-ok">Met</b></div>
            <p className="evidence"><b>README.md</b> ## How to run</p>
            <div className="row-between"><span>Open-source LICENSE file</span><b className="verdict tone-ok">Met</b></div>
            <div className="row-between"><span>Latest build passes</span><b className="verdict tone-bad">Not met</b></div>
            <div className="stamp tone-hold"><strong>Partial release suggested</strong><span>You decide. Nothing moves without your click.</span></div>
          </div>
        </div>
      </section>
      <section className="wrap steps" aria-labelledby="how">
        <h2 id="how">How a milestone works</h2>
        <ol>
          <li><h3>Agree the checks</h3><p>Describe the job. The criteria builder turns it into checks both sides can see. They are locked when the money is reserved.</p></li>
          <li><h3>Reserve with PayPal</h3><p>The client authorizes the amount. PayPal holds it. It is not paid yet, and the freelancer can see it is there.</p></li>
          <li><h3>Submit and verify</h3><p>The freelancer submits a GitHub repo or a document. Code checks the facts. The AI reviews the rest and must quote its evidence.</p></li>
          <li><h3>Release or return</h3><p>The client pays in full, pays part with a reason, asks for changes, or voids the hold. The AI never moves money.</p></li>
        </ol>
      </section>
    </main>
  );
}

function Dashboard({ role, config }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [resetting, setResetting] = useState(false);
  const load = useCallback(() => api.list().then(setItems).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const totals = (items || []).reduce((a, m) => {
    if (m.sample) return a;
    a.reserved += Number(m.money.reserved); a.captured += Number(m.money.captured);
    a.back += Number(m.money.voided) + Number(m.money.released_back); return a;
  }, { reserved: 0, captured: 0, back: 0 });

  const next = (m) => {
    if (m.sample) return "Sample data";
    const mine = { client: { draft: "Reserve the money", verified: "Review the receipt", needs_attention: "Check PayPal" },
                   freelancer: { funded: "Submit your work", revision_requested: "Fix and resubmit" } }[role][m.status];
    return mine ? `Your turn: ${mine.toLowerCase()}` : "";
  };

  return (
    <main className="wrap">
      <div className="page-head">
        <div>
          <h1>Milestones</h1>
          <p className="muted">You are viewing as the {role}. Switch roles at the top right to play the other side.</p>
        </div>
        {role === "client" && <a className="btn" href="#/new">New milestone</a>}
      </div>
      {error && <Banner tone="bad">{error}</Banner>}
      <dl className="totals">
        <div><dt>On hold at PayPal</dt><dd>{money(totals.reserved.toFixed(2))}</dd></div>
        <div><dt>Paid out</dt><dd>{money(totals.captured.toFixed(2))}</dd></div>
        <div><dt>Released back</dt><dd>{money(totals.back.toFixed(2))}</dd></div>
      </dl>
      {!items ? <p className="muted">Loading…</p> : items.length === 0 ? (
        <div className="empty"><p>No milestones yet.</p>{role === "client" && <a className="btn" href="#/new">Create the first one</a>}</div>
      ) : (
        <ul className="rows">
          {items.map((m) => (
            <li key={m.id}>
              <a className="row" href={`#/m/${m.id}`}>
                <div className="row-main">
                  <b>{m.title}</b>
                  <span className="muted small">{m.client} → {m.freelancer}{m.deadline ? ` · due ${m.deadline}` : ""}</span>
                </div>
                <span className="row-next small">{next(m)}</span>
                <span className="row-amt">{money(m.amount, m.currency)}</span>
                <StatusChip status={m.status} />
              </a>
            </li>
          ))}
        </ul>
      )}
      {config.allow_demo_reset && (
        <p className="small muted reset">
          <button className="link" disabled={resetting} onClick={async () => {
            if (!window.confirm("Reset the demo? This deletes every milestone here. Any PayPal holds already made stay at PayPal until they expire.")) return;
            setResetting(true);
            try { await api.reset(); await load(); } catch (e) { setError(e.message); } finally { setResetting(false); }
          }}>Reset demo data</button>
        </p>
      )}
    </main>
  );
}

function NewMilestone({ role, config }) {
  const [f, setF] = useState({ title: "", description: "", amount: "25.00", deadline: "" });
  const [criteria, setCriteria] = useState([]);
  const [note, setNote] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  if (role !== "client") {
    return <main className="wrap"><Banner tone="info">Only the client creates milestones. Switch to Client at the top right.</Banner></main>;
  }
  const suggest = async () => {
    setError(""); setBusy("suggest");
    try {
      const r = await api.suggest(f.description || f.title);
      setCriteria(r.criteria); setNote(r);
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  };
  const create = async (e) => {
    e.preventDefault(); setError(""); setBusy("create");
    try {
      const m = await api.create({ ...f, criteria: criteria.map(({ text, type, check }) => ({ text, type, check })) });
      go(`/m/${m.id}`);
    } catch (err) { setError(err.message); setBusy(""); }
  };
  return (
    <main className="wrap narrow">
      <h1>New milestone</h1>
      <form onSubmit={create} className="form">
        <label>Title<input value={f.title} onChange={set("title")} required minLength={3} maxLength={100} placeholder="Build the booking page" /></label>
        <label>What should the freelancer deliver?
          <textarea rows={5} value={f.description} onChange={set("description")} maxLength={4000}
                    placeholder="Describe the job in plain English or Sinhala. Mention GitHub if you expect code." />
        </label>
        <div className="form-row">
          <label>Amount ({config.paypal.currency})<input value={f.amount} onChange={set("amount")} inputMode="decimal" required pattern="\d+(\.\d{1,2})?" /></label>
          <label>Due date<input type="date" value={f.deadline} onChange={set("deadline")} /></label>
        </div>
        <fieldset>
          <legend>Acceptance criteria</legend>
          <p className="muted small">Both sides see these. They are locked once the money is reserved.</p>
          <button type="button" className="btn ghost" disabled={busy === "suggest" || (f.description + f.title).trim().length < 15} onClick={suggest}>
            {busy === "suggest" ? "Writing criteria…" : criteria.length ? "Suggest again" : "Suggest criteria from the description"}
          </button>
          {note && <Banner tone={note.mode === "ai" ? "info" : "hold"}>{note.mode === "ai" ? "Written by the AI. Edit anything you disagree with." : note.notice}</Banner>}
          <CriteriaEditor value={criteria} onChange={setCriteria} catalog={config.check_catalog} />
          <button type="button" className="link" onClick={() => setCriteria([...criteria, { text: "", type: "manual", check: null }])}>Add a criterion only I can judge</button>
        </fieldset>
        {error && <Banner tone="bad">{error}</Banner>}
        <div className="actions">
          <button className="btn" disabled={busy === "create" || criteria.length === 0}>{busy === "create" ? "Creating…" : "Create milestone"}</button>
          <a className="btn ghost" href="#/dashboard">Cancel</a>
        </div>
      </form>
    </main>
  );
}

function MilestoneDetail({ id, role, config }) {
  const [m, setM] = useState(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const load = useCallback(() => api.get(id).then(setM).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  const update = (next) => { setM(next); setError(""); };

  if (!m) return <main className="wrap">{error ? <Banner tone="bad">{error}</Banner> : <p className="muted">Loading…</p>}</main>;
  const lastReceipt = m.receipts[m.receipts.length - 1];
  const finished = ["paid", "partially_paid", "voided"].includes(m.status);
  const wait = (who, text) => <Banner tone="info">{text} Switch to {who} at the top right to do this.</Banner>;

  return (
    <main className="wrap">
      <p className="crumb"><a href="#/dashboard">Milestones</a></p>
      <div className="page-head">
        <div>
          <h1>{m.title}</h1>
          <p className="muted">{m.client} → {m.freelancer}{m.deadline ? ` · due ${m.deadline}` : ""}{m.sample ? " · sample data" : ""}</p>
        </div>
        <div className="amount-block"><b>{money(m.amount, m.currency)}</b><StatusChip status={m.status} /></div>
      </div>
      {m.description && <p className="desc">{m.description}</p>}
      <MoneyBar m={m.money} total={m.amount} currency={m.currency} />
      {error && <Banner tone="bad" onClose={() => setError("")}>{error}</Banner>}
      {info && <Banner tone="ok" onClose={() => setInfo("")}>{info}</Banner>}
      {m.paypal && m.paypal.simulated && !m.sample && <Banner tone="bad">This hold was made by the simulator, not PayPal.</Banner>}
      {m.status === "needs_attention" && <Banner tone="bad">PayPal's response could not be verified, so this milestone was not marked paid. Check the PayPal sandbox account, then use the log below.</Banner>}
      {m.status === "authorization_expired" && <Banner tone="bad">The PayPal hold has expired, so no more money can be captured from it. Create a new milestone to pay.</Banner>}
      {m.status === "payment_pending" && <Banner tone="hold">PayPal marked the capture as pending. It is not counted as paid until PayPal completes it.</Banner>}

      <section className="block" aria-labelledby="crit">
        <h2 id="crit">Acceptance criteria</h2>
        <CriteriaSection m={m} role={role} config={config} onChange={update} onError={setError} />
      </section>

      {m.status === "draft" && (
        <section className="block" aria-labelledby="fund">
          <h2 id="fund">Reserve the money</h2>
          {role === "client" ? (
            <>
              <p>PayPal will hold {money(m.amount, m.currency)}. Nothing is paid until you release it after reading the proof receipt.</p>
              <PayPalFund config={config} milestone={m} api={api}
                          onFunded={(next) => { update(next); setInfo("Money reserved. The freelancer can now start."); }}
                          onError={setError} />
            </>
          ) : wait("Client", "The client hasn't reserved the money yet.")}
        </section>
      )}

      {(m.status === "funded" || m.status === "revision_requested") && (
        <>
          <HoldInfo m={m} />
          <section className="block" aria-labelledby="sub">
            <h2 id="sub">{m.status === "revision_requested" ? "Resubmit your work" : "Submit your work"}</h2>
            {m.status === "revision_requested" && <Banner tone="hold">The client asked for changes: {lastEvent(m, "revision_requested")}</Banner>}
            {role === "freelancer" ? <SubmitForm m={m} onDone={(n) => { update(n); setInfo("Submitted. The proof receipt is ready for the client."); }} onError={setError} />
              : wait("Freelancer", "Waiting for the freelancer to submit.")}
            {m.status === "funded" && role === "client" && <VoidButton m={m} onDone={update} onError={setError} label="Cancel and release the hold" />}
          </section>
        </>
      )}

      {lastReceipt && (
        <section className="block" aria-labelledby="proof">
          <h2 id="proof">{finished ? "Final proof receipt" : "Proof receipt"}</h2>
          <Receipt receipt={lastReceipt} milestone={m} />
        </section>
      )}

      {m.status === "verified" && (
        <section className="block" aria-labelledby="rel">
          <h2 id="rel">Your decision</h2>
          {role === "client" ? <ReleasePanel m={m} receipt={lastReceipt} onDone={(n, msg) => { update(n); setInfo(msg); }} onError={setError} />
            : wait("Client", "The client is reviewing your proof receipt.")}
        </section>
      )}

      {m.status === "partially_paid" && m.partial_reason && <Banner tone="hold">Reason given for paying less: {m.partial_reason}</Banner>}

      <section className="block" aria-labelledby="log">
        <h2 id="log">Activity log</h2>
        <ol className="log">
          {m.events.map((e, i) => (
            <li key={i}>
              <time>{fmtDate(e.ts)}</time>
              <span><b>{e.type.replace(/_/g, " ")}</b> by {e.actor}{detailText(e.detail)}</span>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}

const lastEvent = (m, type) => {
  const e = [...m.events].reverse().find((x) => x.type === type);
  return e && e.detail && e.detail.reason ? e.detail.reason : "";
};
const detailText = (d) => {
  const parts = Object.entries(d || {}).filter(([, v]) => v !== "" && v !== null).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`);
  return parts.length ? ` · ${parts.join(" · ")}` : "";
};

function HoldInfo({ m }) {
  const p = m.paypal || {};
  if (!p.authorization_id) return null;
  return (
    <Banner tone="info">
      PayPal is holding {money(p.authorized_amount, m.currency)} (authorization {p.authorization_id}).
      PayPal's honor period runs until {fmtDate(p.honor_until)}; the hold itself is valid until {fmtDate(p.expires_at)}.
      Releasing after the honor period can need a reauthorization.
    </Banner>
  );
}

function CriteriaSection({ m, role, config, onChange, onError }) {
  const [draft, setDraft] = useState(m.criteria);
  const [saving, setSaving] = useState(false);
  const editable = m.status === "draft" && role === "client";
  const dirty = JSON.stringify(draft) !== JSON.stringify(m.criteria);
  return (
    <>
      <CriteriaEditor value={editable ? draft : m.criteria} onChange={setDraft} catalog={config.check_catalog} readOnly={!editable} />
      {editable && dirty && (
        <button className="btn ghost" disabled={saving} onClick={async () => {
          setSaving(true);
          try { onChange(await api.editCriteria(m.id, draft.map(({ text, type, check }) => ({ text, type, check })))); }
          catch (e) { onError(e.message); } finally { setSaving(false); }
        }}>Save criteria</button>
      )}
      {m.criteria_frozen
        ? <p className="muted small">Locked when the money was reserved. Criteria hash {m.criteria_hash.slice(0, 16)}.</p>
        : <p className="muted small">You can edit these until the money is reserved.</p>}
    </>
  );
}

function SubmitForm({ m, onDone, onError }) {
  const [kind, setKind] = useState("github");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); onError("");
    try { onDone(await api.submit(m.id, { kind, url, text, filename: "submission.md" })); }
    catch (err) { onError(err.message); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="form">
      <div className="seg-toggle" role="group" aria-label="What are you submitting?">
        <button type="button" className={kind === "github" ? "on" : ""} aria-pressed={kind === "github"} onClick={() => setKind("github")}>GitHub repository</button>
        <button type="button" className={kind === "text" ? "on" : ""} aria-pressed={kind === "text"} onClick={() => setKind("text")}>Document text</button>
      </div>
      {kind === "github" ? (
        <label>Public repository URL
          <input value={url} onChange={(e) => setUrl(e.target.value)} required placeholder="https://github.com/owner/repo" />
          <span className="muted small">ProofPay reads files through GitHub's API. It never downloads or runs your code.</span>
        </label>
      ) : (
        <label>Paste the document
          <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} required minLength={20} />
        </label>
      )}
      <button className="btn" disabled={busy}>{busy ? "Checking your work…" : "Submit for verification"}</button>
    </form>
  );
}

function VoidButton({ m, onDone, onError, label }) {
  const [busy, setBusy] = useState(false);
  return (
    <button className="btn ghost danger" disabled={busy} onClick={async () => {
      if (!window.confirm("Release the PayPal hold? The freelancer will not be paid from this milestone.")) return;
      setBusy(true);
      try { onDone(await api.release(m.id, { action: "void", confirm: true, reason: "Cancelled by client" })); }
      catch (e) { onError(e.message); } finally { setBusy(false); }
    }}>{busy ? "Releasing…" : label}</button>
  );
}

function ReleasePanel({ m, receipt, onDone, onError }) {
  const [mode, setMode] = useState("");
  const [amount, setAmount] = useState(receipt.suggested_amount || "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const rec = receipt.recommendation;
  const act = async (action, body, msg) => {
    setBusy(true); onError("");
    try { onDone(await api.release(m.id, { action, confirm: true, ...body }), msg); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="decision">
      <p>The receipt is a recommendation. Nothing moves until you confirm below.</p>
      <div className="choices">
        <button className={`choice ${rec === "release" ? "suggested" : ""}`} onClick={() => setMode("full")} aria-pressed={mode === "full"}>
          <b>Pay in full</b><span>{money(m.amount, m.currency)} goes to the freelancer</span>
        </button>
        <button className={`choice ${rec === "release_partial" ? "suggested" : ""}`} onClick={() => setMode("partial")} aria-pressed={mode === "partial"}>
          <b>Pay part</b><span>Pay less and return the rest, with a reason</span>
        </button>
        <button className={`choice ${rec === "request_revision" ? "suggested" : ""}`} onClick={() => setMode("revision")} aria-pressed={mode === "revision"}>
          <b>Ask for changes</b><span>No money moves. The freelancer resubmits</span>
        </button>
        <button className="choice" onClick={() => setMode("void")} aria-pressed={mode === "void"}>
          <b>Cancel</b><span>Release the whole hold back to you</span>
        </button>
      </div>
      {mode === "full" && (
        <div className="confirm">
          <p>Capture {money(m.amount, m.currency)} from the PayPal hold. This can't be undone from here.</p>
          <button className="btn" disabled={busy} onClick={() => act("full", {}, "Paid in full. PayPal confirmed the capture.")}>{busy ? "Capturing…" : `Confirm: pay ${money(m.amount, m.currency)}`}</button>
        </div>
      )}
      {mode === "partial" && (
        <div className="confirm form">
          <label>Amount to pay ({m.currency})<input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" />
            {receipt.suggested_amount && <span className="muted small">Suggested from the receipt: {money(receipt.suggested_amount, m.currency)}. Change it if you like.</span>}</label>
          <label>Why are you paying less?<textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} /></label>
          <button className="btn" disabled={busy} onClick={() => act("partial", { amount, reason }, "Partly paid. The rest of the hold was released back.")}>{busy ? "Capturing…" : "Confirm: pay this amount and return the rest"}</button>
        </div>
      )}
      {mode === "revision" && (
        <div className="confirm form">
          <label>What should the freelancer fix?<textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} /></label>
          <button className="btn" disabled={busy} onClick={() => act("revision", { reason }, "Revision requested. The money is still on hold.")}>{busy ? "Sending…" : "Send back for changes"}</button>
        </div>
      )}
      {mode === "void" && (
        <div className="confirm">
          <p>The hold is released and the freelancer is not paid from this milestone.</p>
          <button className="btn danger" disabled={busy} onClick={() => act("void", { reason: "Cancelled by client" }, "Hold released. Nothing was paid.")}>{busy ? "Releasing…" : "Confirm: release the hold"}</button>
        </div>
      )}
    </div>
  );
}
