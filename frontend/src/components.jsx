import React, { useEffect, useRef, useState } from "react";
import { STATUS, fmtDate, money } from "./api.js";

export function StatusChip({ status }) {
  const s = STATUS[status] || { label: status, tone: "idle" };
  return <span className={`chip tone-${s.tone}`}>{s.label}</span>;
}

export function Banner({ tone = "info", children, onClose }) {
  return (
    <div className={`banner tone-${tone}`} role={tone === "bad" ? "alert" : "status"}>
      <div>{children}</div>
      {onClose && <button className="link" onClick={onClose} aria-label="Dismiss">Dismiss</button>}
    </div>
  );
}

/** Reserved / paid / returned, as one bar so the money state is readable at a glance. */
export function MoneyBar({ m, total, currency }) {
  const t = Number(total) || 1;
  const pct = (v) => `${Math.min(100, (Number(v) / t) * 100)}%`;
  return (
    <div className="moneybar">
      <div className="moneybar-track" aria-hidden="true">
        <span className="seg paid" style={{ width: pct(m.captured) }} />
        <span className="seg held" style={{ width: pct(m.reserved) }} />
        <span className="seg back" style={{ width: pct(Number(m.voided) + Number(m.released_back)) }} />
      </div>
      <dl className="moneybar-legend">
        <div><dt><i className="dot paid" />Paid to freelancer</dt><dd>{money(m.captured, currency)}</dd></div>
        <div><dt><i className="dot held" />On hold at PayPal</dt><dd>{money(m.reserved, currency)}</dd></div>
        <div><dt><i className="dot back" />Released back</dt><dd>{money((Number(m.voided) + Number(m.released_back)).toFixed(2), currency)}</dd></div>
      </dl>
    </div>
  );
}

const TYPE_LABEL = { automatic: "Checked by code", ai_review: "Reviewed with evidence", manual: "Your call" };

export function CriteriaEditor({ value, onChange, catalog = {}, readOnly = false }) {
  const update = (i, patch) => onChange(value.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <ul className="criteria">
      {value.map((c, i) => (
        <li key={i} className="criterion">
          <div className="criterion-main">
            {readOnly ? <p>{c.text}</p> : (
              <input aria-label={`Criterion ${i + 1}`} value={c.text} maxLength={240}
                     onChange={(e) => update(i, { text: e.target.value })} />
            )}
            <p className="muted small">
              {TYPE_LABEL[c.type]}
              {!readOnly && c.type === "automatic" && c.check && <> · {catalog[c.check.name] || c.check.name}</>}
            </p>
          </div>
          {!readOnly && c.type === "automatic" && c.check && ["readme_has_section", "file_exists", "min_words", "text_contains"].includes(c.check.name) && (
            <input className="param" aria-label="Check setting" value={c.check.param || ""} maxLength={120}
                   onChange={(e) => update(i, { check: { ...c.check, param: e.target.value } })} />
          )}
          {!readOnly && <button type="button" className="link danger" onClick={() => onChange(value.filter((_, j) => j !== i))}>Remove</button>}
        </li>
      ))}
    </ul>
  );
}

const VERDICT = {
  pass: ["Met", "ok"], fail: ["Not met", "bad"], unclear: ["Unclear", "hold"], needs_client: ["Your call", "info"],
};
const REC = {
  release: ["Release recommended", "ok", "Everything we could check passed."],
  release_partial: ["Partial release suggested", "hold", "Some criteria were not met."],
  request_revision: ["Revision suggested", "bad", "Most criteria were not met."],
  review: ["Review before paying", "info", "Something needs your judgement."],
};

/** The Proof Receipt: styled like a till receipt, because that is what it is. */
export function Receipt({ receipt, milestone }) {
  const [rec, tone, why] = REC[receipt.recommendation] || REC.review;
  const v = receipt.verifier;
  return (
    <article className="receipt" aria-label="Proof receipt">
      <header className="receipt-head">
        <p className="receipt-brand">PROOFPAY</p>
        <p className="receipt-title">Proof receipt</p>
        <p className="receipt-meta">{milestone.title}</p>
        <p className="receipt-meta">{fmtDate(receipt.created_at)}</p>
      </header>
      <div className={`stamp tone-${tone}`}><strong>{rec}</strong><span>{why}</span></div>
      <section>
        <h4>Delivered</h4>
        <p className="receipt-line">{receipt.deliverable.kind === "github" ? "GitHub repo" : "Document"} {receipt.deliverable.label}</p>
        <p className="receipt-line">{receipt.deliverable.ref}</p>
        {receipt.deliverable.commit_date && <p className="receipt-line">Last commit {fmtDate(receipt.deliverable.commit_date)}</p>}
      </section>
      <section>
        <h4>Criteria</h4>
        <ol className="receipt-results">
          {receipt.results.map((r) => {
            const [label, t] = VERDICT[r.verdict] || VERDICT.unclear;
            return (
              <li key={r.criterion_id}>
                <div className="row-between"><span>{r.text}</span><span className={`verdict tone-${t}`}>{label}</span></div>
                <p className="muted small">{r.explanation}</p>
                {r.evidence.map((e, i) => (
                  <p key={i} className={`evidence ${e.verified ? "" : "unverified"}`}>
                    <b>{e.path}</b> {e.quote}{!e.verified && " (quote not found in the files)"}
                  </p>
                ))}
              </li>
            );
          })}
        </ol>
      </section>
      {receipt.injection_flags.length > 0 && (
        <Banner tone="bad">
          The submitted files contain text that looks like instructions to an AI reviewer
          ({receipt.injection_flags.map((f) => f.path).join(", ")}). It was treated as evidence only. Read it before paying.
        </Banner>
      )}
      <section className="receipt-sum">
        <div className="row-between"><span>Met</span><b>{receipt.summary.pass} of {receipt.summary.total}</b></div>
        <div className="row-between"><span>Not met</span><b>{receipt.summary.fail}</b></div>
        <div className="row-between"><span>Unclear</span><b>{receipt.summary.unclear}</b></div>
        <div className="row-between"><span>Your call</span><b>{receipt.summary.needs_client}</b></div>
        {receipt.suggested_amount && <div className="row-between"><span>Suggested payment</span><b>{money(receipt.suggested_amount, milestone.currency)}</b></div>}
      </section>
      <footer className="receipt-foot">
        <p>{v.label}{v.model ? ` · ${v.model}` : ""}</p>
        {v.notice && <p>{v.notice}</p>}
        <p>Criteria hash {receipt.criteria_hash.slice(0, 16)}</p>
        <p>Receipt hash {receipt.receipt_hash.slice(0, 16)}</p>
        <p className="receipt-disclaimer">{receipt.disclaimer}</p>
        <button className="link noprint" onClick={() => window.print()}>Print receipt</button>
      </footer>
    </article>
  );
}

/** Loads the PayPal JS SDK once, with intent=authorize. Only the public client ID reaches the browser. */
function loadPayPalSdk(clientId, currency) {
  if (window.paypal) return Promise.resolve(window.paypal);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=${currency}&intent=authorize&components=buttons`;
    s.onload = () => (window.paypal ? resolve(window.paypal) : reject(new Error("PayPal loaded without a checkout object.")));
    s.onerror = () => reject(new Error("Couldn't load PayPal. Check your connection or ad blocker, and that the sandbox client ID is right."));
    document.head.appendChild(s);
  });
}

export function PayPalFund({ config, milestone, api, onFunded, onError }) {
  const box = useRef(null);
  const [state, setState] = useState("loading");
  const simulated = config.paypal.mode === "simulator";
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (simulated || !config.paypal.configured) { setState("ready"); return undefined; }
    let cancelled = false;
    loadPayPalSdk(config.paypal.client_id, config.paypal.currency)
      .then((paypal) => {
        if (cancelled || !box.current) return;
        box.current.innerHTML = "";
        paypal.Buttons({
          style: { layout: "vertical", shape: "rect", label: "paypal" },
          createOrder: async () => (await api.createOrder(milestone.id)).order_id,
          onApprove: async (data) => {
            try { onFunded(await api.authorize(milestone.id, data.orderID)); }
            catch (e) { onError(e.message); }
          },
          onCancel: () => onError("PayPal checkout was closed. Nothing was held. You can try again."),
          onError: (e) => onError(`PayPal checkout failed: ${e && e.message ? e.message : "unknown error"}`),
        }).render(box.current);
        setState("ready");
      })
      .catch((e) => { if (!cancelled) { setState("error"); onError(e.message); } });
    return () => { cancelled = true; };
  }, [milestone.id, config.paypal.client_id, simulated]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!simulated && !config.paypal.configured) {
    return <Banner tone="hold">PayPal sandbox isn't set up. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to the .env file and restart the backend. See the README, "PayPal sandbox setup".</Banner>;
  }
  if (simulated) {
    return (
      <div>
        <Banner tone="bad">Simulator mode. This is not PayPal and holds no money. Use it only to try the screens.</Banner>
        <button className="btn" disabled={busy} onClick={async () => {
          setBusy(true);
          try { const o = await api.createOrder(milestone.id); onFunded(await api.authorize(milestone.id, o.order_id)); }
          catch (e) { onError(e.message); } finally { setBusy(false); }
        }}>{busy ? "Working…" : "Simulate PayPal approval"}</button>
      </div>
    );
  }
  return (
    <div>
      {state === "loading" && <p className="muted">Loading PayPal…</p>}
      <div ref={box} className="paypal-box" />
      <p className="muted small">Sandbox test money only. Sign in with the sandbox Personal (buyer) account, not your real PayPal.</p>
    </div>
  );
}
